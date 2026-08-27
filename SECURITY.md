
# Vulnerability Scope

- Site Admins and Neighborhood (nbhd) Admins are trusted roles.  They are allowed to do things without concern for security vulnerabilities.

# Code Conventions

- When changing Markdown processing or HTML sanitization logic, bump the `bugfix_rev` var to invalidate existing caches.
- Use urlopen instead of requests in most cases, because we've restricted it to prevent SSRF.
- Sensitive fields should be encrypted (see existing ones for examples).
- Avoid using |safe in jinja templates.  Better to use markupsafe.Markup() around the string when it is first built/loaded.
- Use |tojson in jinja templates when rendering vars into JS.
- Use |escape_markdown in .md.jinja2 templates when rendering user-provided content that should not be interpreted as markdown syntax of the file.
