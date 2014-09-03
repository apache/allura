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
from itertools import groupby
from collections import defaultdict
from operator import itemgetter

from ming.odm import ThreadLocalORMSession

from allura.scripts import ScriptTask
from allura import model as M


log = logging.getLogger(__name__)


class RemoveDuplicateTroves(ScriptTask):
    
    trove_types = [
        'trove_root_database',
        'trove_developmentstatus',
        'trove_audience',
        'trove_license',
        'trove_os',
        'trove_language',
        'trove_topic',
        'trove_natlanguage',
        'trove_environment',
    ]

    @classmethod
    def execute(cls, options):
        duplicates = cls._find_duplicates()
        log.info('Found %s duplicate categories: %s', len(duplicates), duplicates.keys())
        for name, dups in duplicates.iteritems():
            projects_with_category = {}
            for dup in dups:
                projects = cls._projects_with_category(dup._id)
                projects_with_category[dup._id] = projects
            log.info('Following projects are using category %s:', name)
            for _id, ps in projects_with_category.iteritems():
                log.info('  with id %s: %s', _id, [p.shortname for p in ps])
            priority = [(i, len(ps)) for i, ps in projects_with_category.items()]
            priority = sorted(priority, key=itemgetter(1), reverse=True)
            priority = [p[0] for p in priority]
            live, kill = priority[0], priority[1:]
            log.info('%s will live %s will die', live, kill)
            if sum([len(projects_with_category[_id]) for _id in kill]) > 0:
                # Duplicates are used somewhere, need to reasign for all projects that use them
                projects = []
                ids_to_kill = set(kill)
                for p in [projects_with_category[_id] for _id in kill]:
                    projects.extend(p)
                for p in projects:
                    for tt in cls.trove_types:
                        _ids = ids_to_kill.intersection(getattr(p, tt))
                        for _id in _ids:
                            log.info('Removing %s from %s.%s and adding %s instead', _id, p.shortname, tt, live)
                            if not options.dry_run:
                                getattr(p, tt).remove(_id)
                                getattr(p, tt).append(live)
            log.info('Removing categories %s', kill)
            if not options.dry_run:
                M.TroveCategory.query.remove({'_id': {'$in': kill}})
            ThreadLocalORMSession.flush_all()

    @classmethod
    def _find_duplicates(cls):
        dups = []
        agpl = M.TroveCategory.query.find({'shortname': 'agpl'}).all()
        if len(agpl) > 1:
            # agpl is present twice with different cat_id
            # (update in creation command updated only one of duplicates),
            # so code below will not catch it
            dups.extend(agpl)
        for cat in M.TroveCategory.query.find():
            if M.TroveCategory.query.find({
                'shortname': cat.shortname,
                'trove_cat_id': cat.trove_cat_id,
                'trove_parent_id': cat.trove_parent_id,
                'fullname': cat.fullname,
                'fullpath': cat.fullpath,
            }).count() > 1:
                dups.append(cat)
        result = defaultdict(list)
        for k, v in groupby(dups, lambda x: x.shortname):
            result[k].extend(list(v))
        return result

    @classmethod
    def _projects_with_category(cls, _id):
        p = M.Project.query.find({'$or': [
            {'trove_root_database': _id},
            {'trove_developmentstatus': _id},
            {'trove_audience': _id},
            {'trove_license': _id},
            {'trove_os': _id},
            {'trove_language': _id},
            {'trove_topic': _id},
            {'trove_natlanguage': _id},
            {'trove_environment':_id},
        ]})
        return p.all()

    @classmethod
    def parser(cls):
        parser = argparse.ArgumentParser(description='Remove duplicate troves')
        parser.add_argument('--dry-run', action='store_true', dest='dry_run',
                            default=False, help='Print what will be changed but do not change anything')
        return parser


if __name__ == '__main__':
    RemoveDuplicateTroves.main()
