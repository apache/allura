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

from tg import config, app_globals as g
from mock import Mock

from allura.config.app_cfg import AlluraJinjaRenderer
from alluratest.controller import setup_basic_test


def strip_space(s):
    return ''.join(s.split())


class TemplateTest:
    def setup_method(self, method):
        setup_basic_test()
        self.jinja2_env = AlluraJinjaRenderer.create(config, g)['jinja'].jinja2_env


class TestRelatedArtifacts(TemplateTest):

    def _render_related_artifacts(self, artifact):
        html = self.jinja2_env.from_string('''
            {% import 'allura:templates/jinja_master/lib.html' as lib with context %}
            {{ lib.related_artifacts(artifact) }}
        ''').render(artifact=artifact, c=Mock())
        return strip_space(html)

    def test_none(self):
        artifact = Mock(related_artifacts=lambda user: [])
        assert self._render_related_artifacts(artifact) == ''

    def test_simple(self):
        other = Mock()
        other.url.return_value = '/p/test/foo/bar'
        other.project.name = 'Test Project'
        other.app_config.options.mount_label = 'Foo'
        other.link_text.return_value = 'Bar'
        artifact = Mock(related_artifacts=lambda user: [other])
        assert self._render_related_artifacts(artifact) == strip_space('''
            <h4>Related</h4>
            <p>
            <a href="/p/test/foo/bar">Test Project: Foo: Bar</a><br>
            </p>
        ''')

    def test_non_artifact(self):
        # e.g. a commit
        class CommitThing:
            type_s = 'Commit'

            def link_text(self):
                return '[deadbeef]'

            def url(self):
                return '/p/test/code/ci/deadbeef'

        artifact = Mock(related_artifacts=lambda user: [CommitThing()])
        assert self._render_related_artifacts(artifact) == strip_space('''
            <h4>Related</h4>
            <p>
            <a href="/p/test/code/ci/deadbeef">Commit: [deadbeef]</a><br>
            </p>
        ''')
