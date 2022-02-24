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

import logging

log = logging.getLogger(__name__)


class PhoneService:
    """
    Defines the phone verification service interface and provides a default
    no-op implementation.
    """

    def __init__(self, config):
        pass

    def verify(self, number):
        """
        Generate PIN and send it to phone number :param number:

        Returns dict with following keys: status, request_id, error. status is
        either 'ok' or 'error'.

        If status is 'ok' then request_id is present (used later to verify PIN)
        otherwise 'error' is an error message.
        """
        log.info('Phone service is not configured')
        return {
            'status': 'error',
            'error': 'Phone service is not configured',
        }

    def check(self, request_id, pin):
        """
        Given the :param pin: code user entered and :param request_id:
        (obtained by verify), verify that :param pin: is valid.

        Returns dict with following keys: status, error. status is either 'ok'
        or 'error'.

        If status is 'ok' then verification was successful otherwise 'error' is
        an error message.
        """
        log.info('Phone service is not configured')
        return {
            'status': 'error',
            'error': 'Phone service is not configured',
        }

    @classmethod
    def get(cls, config, entry_points):
        """
        Return an instance of PhoneService implementation based on ``config``.
        :rtype: PhoneService
        """
        method = config.get('phone.method')
        if not method:
            return cls(config)
        service = entry_points[method]
        return service(config)
