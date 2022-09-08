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

from allura.model.oauth import dummy_oauths
from allura.scripts import ScriptTask


class CreateOauth1DummyTokens(ScriptTask):

    @classmethod
    def parser(cls):
        return argparse.ArgumentParser(description="Create dummy oauth1 tokens needed by oauthlib implementation")

    @classmethod
    def execute(cls, options):
        dummy_oauths()
        print('Done')


if __name__ == '__main__':
    CreateOauth1DummyTokens.main()
