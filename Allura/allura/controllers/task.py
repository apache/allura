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



import six


class TaskController:

    '''WSGI app providing web-like RPC

    The purpose of this app is to allow us to replicate the
    normal web request environment as closely as possible
    when executing taskd tasks.
    '''

    def __call__(self, environ, context):
        # see TGController / CoreDispatcher for reference on how this works on a normal controllers

        task = environ['task']
        nocapture = environ['nocapture']
        result = task(restore_context=False, nocapture=nocapture)
        py_response = context.response
        py_response.headers['Content-Type'] = 'text/plain'  # `None` default is problematic for some middleware
        py_response.body = six.ensure_binary(result or b'')
        return py_response
