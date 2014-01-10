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

'''Merge all the OldProjectRole collections in into a ProjectRole collection.
'''
import logging

from ming.orm import session, state
from allura import model as M

log = logging.getLogger(__name__)

log.info('Moving project roles in database %s to main DB',
         M.Project.database_uri())
for opr in M.OldProjectRole.query.find():
    pr = M.ProjectRole(**state(opr).document)
session(opr).clear()
session(pr).flush()
session(pr).clear()
