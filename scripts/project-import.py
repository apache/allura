#       Licensed to the Apache Software Foundation (ASF) under one
#       or more contributor license agreements.  See the NOTICE file
#       distributed with this work for additional information
#       regarding copyright ownership.  The ASF licenses this file
#       to you under the Apache License, Version 2.0 (the
#       "License"); you may not use this file except in compliance
#       with the License.  You may obtain a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#       Unless required by applicable law or agreed to in writing,
#       software distributed under the License is distributed on an
#       "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
#       KIND, either express or implied.  See the License for the
#       specific language governing permissions and limitations
#       under the License.

from __future__ import unicode_literals
from __future__ import absolute_import
import bson
import datetime
import json
import logging
import multiprocessing
import re
import string
import sys

import colander as col
from ming.orm import session, ThreadLocalORMSession
from tg import tmpl_context as c, app_globals as g

from allura import model as M
from allura.lib import helpers as h
from allura.lib.plugin import ProjectRegistrationProvider
import six
from io import open
from six.moves import range

log = logging.getLogger(__name__)


class TroveCategory():

    def __init__(self, root_type=''):
        self.root_type = root_type

    def deserialize(self, node, cstruct):
        if cstruct is col.null:
            return col.null
        cat = M.TroveCategory.query.get(fullpath=cstruct)
        if not cat:
            cat = M.TroveCategory.query.get(fullname=cstruct)
        if not cat:
            raise col.Invalid(node,
                              '"%s" is not a valid trove category.' % cstruct)
        if not cat.fullpath.startswith(self.root_type):
            raise col.Invalid(node,
                              '"%s" is not a valid "%s" trove category.' %
                              (cstruct, self.root_type))
        return cat


class User():

    def deserialize(self, node, cstruct):
        if cstruct is col.null:
            return col.null
        user = M.User.by_username(cstruct)
        if not user:
            raise col.Invalid(node,
                              'Invalid username "%s".' % cstruct)
        return user


class ProjectName(object):

    def __init__(self, name, shortname):
        self.name = name
        self.shortname = shortname


class ProjectNameType():

    def deserialize(self, node, cstruct):
        if cstruct is col.null:
            return col.null
        name = cstruct
        shortname = re.sub("[^A-Za-z0-9 ]", "", name).lower()
        shortname = re.sub(" ", "-", shortname)
        return ProjectName(name, shortname)


class ProjectShortnameType():

    def __init__(self, nbhd, update):
        self.nbhd = nbhd
        self.update = update

    def deserialize(self, node, cstruct):
        if cstruct is col.null:
            return col.null
        return ProjectRegistrationProvider.get().shortname_validator.to_python(cstruct,
                                                                               check_allowed=not self.update,
                                                                               neighborhood=self.nbhd)


class Award():

    def __init__(self, nbhd):
        self.nbhd = nbhd

    def deserialize(self, node, cstruct):
        if cstruct is col.null:
            return col.null
        award = M.Award.query.find(dict(short=cstruct,
                                        created_by_neighborhood_id=self.nbhd._id)).first()
        if not award:
            # try to look up the award by _id
            award = M.Award.query.find(dict(_id=bson.ObjectId(cstruct),
                                            created_by_neighborhood_id=self.nbhd._id)).first()
        if not award:
            raise col.Invalid(node,
                              'Invalid award "%s".' % cstruct)
        return award


class TroveTopics(col.SequenceSchema):
    trove_topics = col.SchemaNode(TroveCategory("Topic"))


class TroveLicenses(col.SequenceSchema):
    trove_license = col.SchemaNode(TroveCategory("License"))


class TroveDatabases(col.SequenceSchema):
    trove_databases = col.SchemaNode(TroveCategory("Database Environment"))


class TroveStatuses(col.SequenceSchema):
    trove_statuses = col.SchemaNode(TroveCategory("Development Status"))


class TroveAudiences(col.SequenceSchema):
    trove_audience = col.SchemaNode(TroveCategory("Intended Audience"))


class TroveOSes(col.SequenceSchema):
    trove_oses = col.SchemaNode(TroveCategory("Operating System"))


class TroveLanguages(col.SequenceSchema):
    trove_languages = col.SchemaNode(TroveCategory("Programming Language"))


class TroveTranslations(col.SequenceSchema):
    trove_translations = col.SchemaNode(TroveCategory("Translations"))


class TroveUIs(col.SequenceSchema):
    trove_uis = col.SchemaNode(TroveCategory("User Interface"))


class Labels(col.SequenceSchema):
    label = col.SchemaNode(col.Str())


class Project(col.MappingSchema):
    name = col.SchemaNode(ProjectNameType())
    summary = col.SchemaNode(col.Str(), missing='')
    description = col.SchemaNode(col.Str(), missing='')
    admin = col.SchemaNode(User())
    private = col.SchemaNode(col.Bool(), missing=False)
    labels = Labels(missing=[])
    external_homepage = col.SchemaNode(col.Str(), missing='')
    video_url = col.SchemaNode(col.Str(), missing='')
    trove_root_databases = TroveDatabases(missing=None)
    trove_developmentstatuses = TroveStatuses(validator=col.Length(max=6), missing=None)
    trove_audiences = TroveAudiences(validator=col.Length(max=6), missing=None)
    trove_licenses = TroveLicenses(validator=col.Length(max=6), missing=None)
    trove_oses = TroveOSes(missing=None)
    trove_languages = TroveLanguages(validator=col.Length(max=6), missing=None)
    trove_topics = TroveTopics(validator=col.Length(max=3), missing=None)
    trove_natlanguages = TroveTranslations(missing=None)
    trove_environments = TroveUIs(missing=None)
    tool_data = col.SchemaNode(col.Mapping(unknown='preserve'), missing={})
    icon = col.SchemaNode(col.Str(), missing=None)
    # more fields are added dynamically to the schema in main()


def valid_shortname(project):
    if project.shortname:
        # already validated in ProjectShortnameType validator
        return True
    elif 3 <= len(project.name.shortname) <= 15:
        return True
    else:
        return 'Project shortname "%s" must be between 3 and 15 characters' \
            % project.name.shortname


class Projects(col.SequenceSchema):
    project = Project(validator=col.Function(valid_shortname))


class Object(object):

    def __init__(self, d):
        self.__dict__.update(d)


def trove_ids(orig, new_):
    if new_ is None:
        return orig
    return list(set(t._id for t in list(new_)))


def create_project(p, nbhd, options):
    worker_name = multiprocessing.current_process().name
    M.session.artifact_orm_session._get().skip_mod_date = True
    shortname = p.shortname or p.name.shortname
    project = M.Project.query.get(shortname=shortname,
                                  neighborhood_id=nbhd._id)
    project_template = nbhd.get_project_template()

    if project and not (options.update and p.shortname):
        log.warning('[%s] Skipping existing project "%s". To update an existing '
                    'project you must provide the project shortname and run '
                    'this script with --update.' % (worker_name, shortname))
        return 0

    if not project:
        log.info('[%s] Creating project "%s".' % (worker_name, shortname))
        try:
            project = nbhd.register_project(shortname,
                                            p.admin,
                                            project_name=p.name.name,
                                            private_project=p.private)
        except Exception as e:
            log.exception('[%s] %s' % (worker_name, str(e)))
            return 0
    else:
        log.info('[%s] Updating project "%s".' % (worker_name, shortname))

    project.notifications_disabled = True

    if options.ensure_tools and 'tools' in project_template:
        for i, tool in enumerate(six.iterkeys(project_template['tools'])):
            tool_config = project_template['tools'][tool]
            if project.app_instance(tool_config['mount_point']):
                continue
            tool_options = tool_config.get('options', {})
            for k, v in six.iteritems(tool_options):
                if isinstance(v, six.string_types):
                    tool_options[k] = string.Template(v).safe_substitute(
                        project.root_project.__dict__.get('root_project', {}))
            project.install_app(tool,
                                mount_label=tool_config['label'],
                                mount_point=tool_config['mount_point'],
                                **tool_options)

    project.summary = p.summary
    project.short_description = p.description
    project.external_homepage = p.external_homepage
    project.video_url = p.video_url
    project.last_updated = datetime.datetime.utcnow()
    # These properties may have been populated by nbhd template defaults in
    # register_project(). Overwrite if we have data, otherwise keep defaults.
    project.labels = p.labels or project.labels
    project.trove_root_database = trove_ids(project.trove_root_database, p.trove_root_databases)
    project.trove_developmentstatus = trove_ids(project.trove_developmentstatus, p.trove_developmentstatuses)
    project.trove_audience = trove_ids(project.trove_audience, p.trove_audiences)
    project.trove_license = trove_ids(project.trove_license, p.trove_licenses)
    project.trove_os = trove_ids(project.trove_os, p.trove_oses)
    project.trove_language = trove_ids(project.trove_language, p.trove_languages)
    project.trove_topic = trove_ids(project.trove_topic, p.trove_topics)
    project.trove_natlanguage = trove_ids(project.trove_natlanguage, p.trove_natlanguages)
    project.trove_environment = trove_ids(project.trove_environment, p.trove_environments)

    project.tool_data.update(p.tool_data)

    for a in p.awards:
        M.AwardGrant(app_config_id=bson.ObjectId(),
                     award_id=a._id,
                     granted_to_project_id=project._id,
                     granted_by_neighborhood_id=nbhd._id)

    if p.icon:
        with open(p.icon, 'rb') as icon_file:
            project.save_icon(p.icon, icon_file)

    project.notifications_disabled = False
    with h.push_config(c, project=project, user=p.admin):
        ThreadLocalORMSession.flush_all()
        g.post_event('project_updated')
    session(project).clear()
    return 0


def create_projects(projects, nbhd, options):
    for p in projects:
        r = create_project(Object(p), nbhd, options)
        if r != 0:
            sys.exit(r)


def main(options):
    log.addHandler(logging.StreamHandler(sys.stdout))
    log.setLevel(getattr(logging, options.log_level.upper()))
    log.debug(options)

    nbhd = M.Neighborhood.query.get(name=options.neighborhood)
    if not nbhd:
        return 'Invalid neighborhood "%s".' % options.neighborhood

    data = json.load(open(options.file, 'r'))

    # dynamically add to the schema (e.g. if needs nbhd)
    project = Project()
    project.add(col.SchemaNode(col.Sequence(),
                               col.SchemaNode(Award(nbhd)),
                               name='awards', missing=[]))
    project.add(col.SchemaNode(ProjectShortnameType(nbhd, options.update),
                               name='shortname', missing=None))

    projects = []
    for datum in data:
        try:
            projects.append(project.deserialize(datum))
        except Exception:
            keep_going = options.validate_only
            log.error('Error on %s\n%s', datum['shortname'], datum, exc_info=keep_going)
            if not keep_going:
                raise

    log.debug(projects)

    if options.validate_only:
        return

    chunks = [projects[i::options.nprocs] for i in range(options.nprocs)]
    jobs = []
    for i in range(options.nprocs):
        p = multiprocessing.Process(target=create_projects,
                                    args=(chunks[i], nbhd, options), name='worker-' + str(i + 1))
        jobs.append(p)
        p.start()

    for j in jobs:
        j.join()
        if j.exitcode != 0:
            return j.exitcode
    return 0


def parse_options():
    import argparse
    parser = argparse.ArgumentParser(
        description='Import Allura project(s) from JSON file')
    parser.add_argument('file', metavar='JSON_FILE', type=str,
                        help='Path to JSON file containing project data.')
    parser.add_argument('neighborhood', metavar='NEIGHBORHOOD', type=str,
                        help='Destination Neighborhood shortname.')
    parser.add_argument('--log', dest='log_level', default='INFO',
                        help='Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL).')
    parser.add_argument('--update', dest='update', default=False,
                        action='store_true',
                        help='Update existing projects. Without this option, existing '
                        'projects will be skipped.')
    parser.add_argument('--ensure-tools', dest='ensure_tools', default=False,
                        action='store_true',
                        help='Check nbhd project template for default tools, and install '
                        'them on the project(s) if not already installed.')
    parser.add_argument(
        '--nprocs', '-n', action='store', dest='nprocs', type=int,
        help='Number of processes to divide the work among.',
        default=multiprocessing.cpu_count())
    parser.add_argument('--validate-only', '-v', action='store_true', dest='validate_only',
                        help='Validate ALL records, make no changes')
    return parser.parse_args()


if __name__ == '__main__':
    sys.exit(main(parse_options()))
