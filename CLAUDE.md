# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Apache Allura is an open source software "forge" (à la SourceForge/GitHub): source repo hosting (Git/SVN/Hg),
ticket tracker, wiki, discussion forums, blog, and more, organized into projects/neighborhoods. It's a Python
web app built on TurboGears 2, MongoDB (via the Ming ODM), and Solr for search — extended via a plugin
("tool") architecture.

## Repository layout

This is a multi-package monorepo. Each top-level directory is an independently `pip install`-able package:

- `Allura/` — the core platform: web framework glue, models, auth, permissions, task/event bus, base
  controllers, templates. Everything else depends on this.
- `AlluraTest/` — shared test harness/fixtures (`alluratest.controller`) used by every other package's tests.
- `Forge*/` (ForgeTracker, ForgeWiki, ForgeDiscussion, ForgeGit, ForgeSVN, ForgeBlog, ForgeChat, ForgeActivity,
  ForgeLink, ForgeShortUrl, ForgeFiles, ForgeFeedback, ForgeUserStats, ForgeImporters) — individual "tools"
  (plugins) that plug into the core platform. Each has its own `setup.py`/`pyproject.toml`, own package dir
  (lowercase, e.g. `forgetracker/`), own tests, and its own `*.egg-info`.
- `scm_config/`, `solr_config/` — config for git/http and Solr, used by the Docker dev environment.
- `scripts/` — one-off admin/migration scripts (run with the app's Python env), e.g.
  `scripts/convert_encrypted_field.py`, `scripts/migrations/`.

Each Forge package registers itself with the core platform via entry points declared in its
`pyproject.toml` (older packages may still show these in `setup.cfg`/`*.egg-info`), most importantly:
```toml
[project.entry-points.allura]
Tickets = "forgetracker.tracker_main:ForgeTrackerApp"
```
To find the root controller for a tool, look up its `[project.entry-points.allura]` entry, find that
`Application` subclass, and look at its `root` attribute.

## Setup / running locally

Full install instructions are in `Allura/docs/getting_started/installation.rst` (or the Docker equivalent
`install_each_step.rst`/README) — not worth duplicating here. In short, a working system needs MongoDB, Solr,
and the Allura web app + `taskd` background worker all running. `docker-compose.yml` defines all of these
services (`web`, `taskd`, `solr`, `mongo`, `outmail`, `inmail`, `http`).

Key `.ini` config files live in `Allura/`: `development.ini` (local dev), `test.ini` (tests),
`docker-dev.ini` (docker dev), `production-docker-example.ini`.

To run the web/taskd processes in the foreground for interactive debugging (e.g. with `ipdb`):
```bash
cd Allura
gunicorn --reload --paste development.ini -b :8080     # web
paster taskd development.ini --nocapture                # taskd (background tasks/events)
```
Docker equivalents are in `Allura/docs/development/contributing.rst`.

## Tests

Tests use `pytest`. Run everything from the repo root:
```bash
./run_tests                 # all packages, in parallel, plus npm run lint-es6
./run_tests -p ForgeTracker # just one package
./run_tests --coverage      # with coverage
./run_tests -n X # number of processes to be used per suite
./run_tests -m X # number of parallel processes to be used per suite
```
Or run a single package/test directly (faster while iterating):
```bash
cd ForgeTracker && pytest
cd ForgeTracker && pytest forgetracker/tests/functional/test_root.py::TestRootController::test_new_ticket -v
```
Notes:
- `AlluraTest` always runs first (it's imported by everything else; catches syntax errors early).
- `ForgeGit` and `ForgeSVN` are NOT safe to run with `pytest-xdist` multiprocessing (`run_tests` handles
  this automatically).
- Functional/controller tests subclass `allura.tests.TestController`; its `self.app` is a WebTest app with
  `c.project` preset to the `test` project and `c.user` preset to `test-admin`. Tools under test are
  mounted at `/<entry point name>/`.
- Model/unit tests that need `c`/`g` but not a full WSGI app use
  `alluratest.controller.setup_unit_test()` + `allura.lib.helpers.set_context(...)`.
- Tasks and event handlers are normal Python callables (decorated with `@task`/`@event_handler`) — test them
  by calling directly rather than spinning up `taskd`.
- See `Allura/docs/development/testing.rst` for more detail.

## Linting

- Python: `ruff` (config in `ruff.toml`, line length 119, py310 target). Notable repo-wide conventions
  enforced via pre-commit rather than ruff: use `.utcnow()`/`.utcfromtimestamp()`/`calendar.timegm()`, never
  `.now()`/`.fromtimestamp()`/`.mktime()` (timezone-safety rule, checked by `pre-commit`'s local `tz-functions`
  hook and mirrored in `test_syntax.py`).
- JS/SCSS: `npm run lint-es5`, `npm run lint-es6` (or `npm run lint` for both).
- Jinja templates are linted with `j2lint` via pre-commit.
- `.pre-commit-config.yaml` is the source of truth for all of the above; run `pre-commit run --all-files`
  to check everything at once.

## Frontend build

JS/CSS is built with Broccoli + Babel (ES6) and node-sass, orchestrated via `Brocfile.js`/`package.json`:
```bash
npm run watch          # transpile ES6 JS on change (needed while editing frontend code)
npm run css-watch       # compile SCSS on change
npm run build           # one-off JS build
```
Uses React + ES6 for newer frontend code; jQuery/plain JS + Jinja2 templates for older/most pages.

## Core architecture concepts

**Request context (`c` / `g`)** — TurboGears sets up a per-request context object `c` with `c.project`,
`c.app` (current tool instance), and `c.user`. `g` is the app-globals singleton (`allura.lib.app_globals`).
`allura.lib.helpers.set_context(project_id, mount_point=..., app_config_id=...)` and the `push_config`
context manager are how you change/restore these outside of normal request dispatch (e.g. in scripts/tests).
Request dispatch for *everything* starts at `Allura/allura/controllers/root.py` (`RootController`), which
does neighborhood/project lookup via `_lookup`, then dispatches into the matched tool's own root controller.

**Tools (`allura.app.Application`)** — Each Forge package's main class subclasses `Application` and is the
extension point tying a plugin into a project: it defines the tool's root controller, permissions, sitemap
entries, config options, and lifecycle hooks. Registered via the `[project.entry-points.allura]` entry point.

**Artifacts (`allura.model.artifact.Artifact`)** — The base class for anything a tool stores that should be
searchable/linkable (wiki pages, tickets, forum posts, commits, etc). Subclassing it gets you automatic Solr
indexing, shortlink generation (`[#151]`, `[MyWikiPage]`, cross-tool via `[mount_point:#151]`), and ACL
support. Override `url()`, `index()`, `shorthand_id()` at minimum.

**Ming ODM (MongoDB)** — All persistence is through Ming (`allura/model/`), which mimics native MongoDB query
syntax closely. `session.py` and `__mongometa__` per-model define collection/index config.

**Async processing: tasks vs. events** (`Allura/docs/platform/message_bus.rst`) — Two decorators:
  - `@task` — a plain function; `.post(*args, **kwargs)` schedules it as a `MonQTask` doc in Mongo for the
    `taskd` daemon to execute later; calling it directly (no `.post`) just runs it synchronously (used a lot
    in tests).
  - `@event_handler('name')` — fan-out: many handlers can listen to the same named event.
    `g.post_event('name', *args, **kwargs)` schedules the fan-out task; the event name is always the handler's
    first positional arg.
  `taskd` (paster command) is the worker process that executes both.

**Permissions** (`Allura/docs/platform/permissions.rst`) — Users belong to per-project groups/roles, each
with a list of permission strings. Permissions are additive down the project/subproject hierarchy and via
per-artifact ACLs — child scopes can only *grant* more access, never revoke inherited access. Checked via
predicate functions like `has_project_access(obj, permission)` / `allura.lib.security.has_access`.

**Email integration** — Every tool mounted in a project gets its own inbound email address
(`<topic>@<mount_point>[.<subproject>].<project>.<domain>`); inbound mail is parsed and routed to
`c.app.handle_message(topic, msg)` after an `c.app.has_access(user, topic)` check. Outbound mail is sent by
posting the `allura.tasks.mail_tasks.sendmail` task (do not use smtplib directly).

**Markdown macros** — Custom `[[macro_name]]` commands in Markdown content. Defined with
`@macro()` from `allura.lib.macro` and registered via a `[project.entry-points."allura.macros"]` entry point;
see `allura.lib.macro` for existing examples.

**Extension points** — Besides tools/artifacts, Allura supports pluggable theme providers, auth providers,
project-registration providers, spam filters, phone/2FA services, WSGI middleware, and more — all wired via
entry points. Full list in `Allura/docs/development/extending.rst`.

## Miscellaneous conventions

- Timezone safety: always use UTC-explicit datetime functions (see Linting section above) — this is enforced
  by pre-commit and `test_syntax.py`, not by ruff itself.
- License headers: nearly every source file carries an ASF license header; `rat-excludes.txt` lists what's
  exempt. Keep new files consistent with neighboring files' headers.
- Sensitive fields (e.g. user email) may be stored with field-level encryption — see
  `Allura/allura/model/auth.py` and `scripts/convert_encrypted_field.py` for the pattern used when adding new
  encrypted fields.
