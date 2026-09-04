<!--
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
-->

# Vulnerability Scope

- Site Admins and Neighborhood (nbhd) Admins are trusted roles.  They are allowed to do things without concern for security vulnerabilities.
- Allura runs with TurboGears and WebOb.  HTTP vulnerabilities must be tested with a full stack (self.app.get or manual in browser)
- Features that are disabled by default (e.g. Trac importer) are not subject to vulnerability reports

# Code Conventions

- When changing Markdown processing or HTML sanitization logic, bump the `bugfix_rev` var to invalidate existing caches.
- Use urlopen instead of requests in most cases, because we've restricted it to prevent SSRF.
- Sensitive fields should be encrypted (see existing ones for examples).
- Avoid using |safe in jinja templates.  Better to use markupsafe.Markup() around the string when it is first built/loaded.
- Use |tojson in jinja templates when rendering vars into JS.
- Use |escape_markdown in .md.jinja2 templates when rendering user-provided content that should not be interpreted as markdown syntax of the file.
