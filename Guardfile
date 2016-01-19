=begin
    Licensed to the Apache Software Foundation (ASF) under one
    or more contributor license agreements.  See the NOTICE file
    distributed with this work for additional information
    regarding copyright ownership.  The ASF licenses this file
    to you under the Apache License, Version 2.0 (the
    "License"); you may not use this file except in compliance
    with the License.  You may obtain a copy of the License at

     http://www.apache.org/licenses/LICENSE-2.0

    Unless required by applicable law or agreed to in writing,
    software distributed under the License is distributed on an
    "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
    KIND, either express or implied.  See the License for the
    specific language governing permissions and limitations
    under the License.
=end

# More info at https://github.com/guard/guard#readme

ignore %r{^node_modules/}, %r{^env.*/}, %r{/tests/data/}, %r{.+\.pyc?}, %r{^Allura/docs/}, %r{.+\.log}, %r{.+\.ini}

# For autoreload of your browser, upon html/js/css changes:
#   Install http://livereload.com/extensions/
#   gem install guard-livereload
#   Then run `guard` and enable the page in your browser.
guard 'livereload' do
  watch(%r{.+\.js})
  watch(%r{.+\.css})
  watch(%r{.+\.html})
end
