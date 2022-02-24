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

from io import BytesIO

import datetime
import string
import logging
try:
    from typing import Union
except ImportError:  # py2 doesn't have typing yet
    pass

import colander as col
import bson
import requests
import formencode
import six
from six.moves.urllib.parse import urlparse

from allura.lib.helpers import slugify
from allura.model import Neighborhood
from ming.base import Object
from ming.orm import ThreadLocalORMSession
from tg import tmpl_context as c, app_globals as g

from allura import model as M
from allura.lib import helpers as h
from allura.lib.plugin import ProjectRegistrationProvider


log = logging.getLogger(__name__)


"""
Validators and helpers for adding projects via the API or project-import.py script
"""


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


class NewProjectSchema(col.MappingSchema):
    def schema_type(self, **kw):
        return col.Mapping(unknown='raise')

    name = col.SchemaNode(col.Str())
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
    icon_url = col.SchemaNode(col.Str(), missing=None, validator=col.url)
    # more fields are added dynamically to the schema in make_newproject_schema()


def trove_ids(orig, new_):
    if new_ is None:
        return orig
    return list({t._id for t in list(new_)})


def make_newproject_schema(nbhd, update=False):
    # type: (Neighborhood, bool) -> NewProjectSchema
    projectSchema = NewProjectSchema(unknown='raise')
    # dynamically add to the schema fields that depend on `nbhd`
    projectSchema.add(col.SchemaNode(col.Sequence(),
                                     col.SchemaNode(Award(nbhd)),
                                     name='awards', missing=[]))
    projectSchema.add(col.SchemaNode(ProjectShortnameType(nbhd, update),
                                     name='shortname', missing=None))
    return projectSchema


def deserialize_project(datum, projectSchema, nbhd):
    # type: (dict, NewProjectSchema, Neighborhood) -> object
    p = projectSchema.deserialize(datum)
    p = Object(p)  # convert from dict to something with attr-access

    # generate a shortname, and try to make it unique
    if not p.shortname:
        max_shortname_len = 15  # maybe more depending on NeighborhoodProjectShortNameValidator impl, but this is safe
        shortname = orig_shortname = make_shortname(p.name, max_shortname_len)
        for i in range(1, 10):
            try:
                ProjectRegistrationProvider.get().shortname_validator.to_python(shortname, neighborhood=nbhd)
            except formencode.api.Invalid:
                if len(orig_shortname) == max_shortname_len - 1:
                    shortname = orig_shortname + str(i)
                else:
                    shortname = orig_shortname[:max_shortname_len - 1] + str(i)
            else:
                # we're good!
                break
        p.shortname = shortname

    return p


def make_shortname(name, max_len):
    # lowercase, drop periods and underscores
    shortname = slugify(name)[1].replace('_', '-')
    # must start with a letter
    if not shortname[0].isalpha():
        shortname = 'a-' + shortname
    # truncate length, avoid trailing dash
    shortname = shortname[:max_len].rstrip('-')
    # too short
    if len(shortname) < 3:
        shortname += '-z'
    return shortname


def create_project_with_attrs(p, nbhd, update=False, ensure_tools=False):
    # type: (object, M.Neighborhood, bool, bool) -> Union[M.Project|bool]
    M.session.artifact_orm_session._get().skip_mod_date = True
    shortname = p.shortname
    project = M.Project.query.get(shortname=shortname,
                                  neighborhood_id=nbhd._id)
    project_template = nbhd.get_project_template()

    if project and not update:
        log.warning('Skipping existing project "%s"' % (shortname))
        return False

    if not project:
        creating = True
        project = nbhd.register_project(shortname,
                                        p.admin,
                                        project_name=p.name,
                                        private_project=p.private,
                                        omit_event=True,  # because we'll fire it later after setting other fields
                                        )
    else:
        creating = False
        log.info('Updating project "%s".' % (shortname))

    project.notifications_disabled = True

    if ensure_tools and 'tools' in project_template:
        for i, tool in enumerate(project_template['tools'].keys()):
            tool_config = project_template['tools'][tool]
            if project.app_instance(tool_config['mount_point']):
                continue
            tool_options = tool_config.get('options', {})
            for k, v in tool_options.items():
                if isinstance(v, str):
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

    if p.icon_url:
        req = requests.get(p.icon_url)
        req.raise_for_status()
        project.save_icon(urlparse(p.icon_url).path,
                          BytesIO(req.content),
                          content_type=req.headers.get('Content-Type'))
    elif getattr(p, 'icon', None):
        with open(p.icon, 'rb') as icon_file:
            project.save_icon(p.icon, icon_file)

    project.notifications_disabled = False
    with h.push_config(c, project=project, user=p.admin):
        ThreadLocalORMSession.flush_all()
        if creating:
            g.post_event('project_created')
        else:
            g.post_event('project_updated')
    return project
