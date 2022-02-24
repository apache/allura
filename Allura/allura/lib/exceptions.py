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

import webob.exc
from formencode import Invalid


class ForgeError(Exception):
    pass


class ProjectConflict(ForgeError, Invalid):

    # support the single string constructor in addition to full set of params
    # that Invalid.__init__ requires
    def __init__(self, msg, value=None, state=None, error_list=None, error_dict=None):
        super().__init__(
            msg, value, state, error_list, error_dict)


class ProjectShortnameInvalid(ForgeError, Invalid):
    pass


class ProjectOverlimitError(ForgeError):
    pass


class RatelimitError(ForgeError):
    pass


class ProjectRatelimitError(RatelimitError):
    pass


class MultifactorRateLimitError(RatelimitError):
    pass


class ProjectPhoneVerificationError(ForgeError):
    pass


class ToolError(ForgeError):
    pass


class NoSuchProjectError(ForgeError):
    pass


class NoSuchNeighborhoodError(ForgeError):
    pass


class NoSuchGlobalsError(ForgeError):
    pass


class MailError(ForgeError):
    pass


class AddressException(MailError):
    pass


class NoSuchNBFeatureError(ForgeError):
    pass


class InvalidNBFeatureValueError(ForgeError):
    pass


class InvalidRecoveryCode(ForgeError):
    pass


class CompoundError(ForgeError):

    def __repr__(self):
        return '<{}>\n{}\n</{}>'.format(
            self.__class__.__name__,
            '\n'.join(map(repr, self.args)),
            self.__class__.__name__)

    def format_error(self):
        import traceback
        parts = ['<%s>\n' % self.__class__.__name__]
        for tp, val, tb in self.args:
            for line in traceback.format_exception(tp, val, tb):
                parts.append('    ' + line)
        parts.append('</%s>\n' % self.__class__.__name__)
        return ''.join(parts)


class HTTPTooManyRequests(webob.exc.HTTPClientError):
    code = 429
    title = 'Too Many Requests'
    explanation = 'Too Many Requests'
