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

from bson import ObjectId

import logging

from ming.odm import ThreadLocalORMSession

from allura import model as M

log = logging.getLogger(__name__)


def main():
    email_addresses = M.EmailAddress.query.find(dict(email=None)).all()
    for email in email_addresses:
        email.email = email._id
        email._id = ObjectId()
        ThreadLocalORMSession.flush_all()
    ThreadLocalORMSession.close_all()


if __name__ == '__main__':
    main()
