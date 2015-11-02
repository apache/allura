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

import argparse
import logging

from ming.odm import Mapper, session
from pylons import app_globals as g

from allura.scripts import ScriptTask
from allura import model as M
from allura.tasks.index_tasks import solr_del_project_artifacts


log = logging.getLogger(__name__)


class DeleteProjects(ScriptTask):

    @classmethod
    def execute(cls, options):
        for proj in options.projects:
            proj = cls.get_project(proj)
            if proj:
                log.info('Purging %s%s', proj.neighborhood.url_prefix, proj.shortname)
                cls.purge_project(proj)

    @classmethod
    def get_project(cls, proj):
        n, p = proj.split('/')
        n = M.Neighborhood.query.get(url_prefix='/{}/'.format(n))
        if not n:
            log.warn("Can't find neighborhood for %s", proj)
            return
        p = M.Project.query.get(neighborhood_id=n._id, shortname=p)
        if not p:
            log.warn("Can't find project %s", proj)
            return
        return p

    @classmethod
    def purge_project(cls, project):
        pid = project._id
        solr_del_project_artifacts.post(pid)
        app_config_ids = [ac._id for ac in M.AppConfig.query.find(dict(project_id=pid))]
        for m in Mapper.all_mappers():
            cls = m.mapped_class
            if 'project_id' in m.property_index:
                # Purge the things directly related to the project
                cls.query.remove(dict(project_id=pid))
            elif 'app_config_id' in m.property_index:
                # ... and the things related to its apps
                cls.query.remove(dict(app_config_id={'$in': app_config_ids}))
        project.delete()
        session(project).flush()
        g.post_event('project_deleted', project_id=pid)

    @classmethod
    def parser(cls):
        parser = argparse.ArgumentParser(description='Completely delete projects')
        parser.add_argument('projects', metavar='nbhd/project', type=str, nargs='+',
                            help='Project to delete in a form nbhd_prefix/shortname')
        return parser


def get_parser():
    return DeleteProjects.parser()


if __name__ == '__main__':
    DeleteProjects.main()
