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

Sibling repos extend this one as plugins rather than living in this monorepo: SourceForge's commercial
layer `forge-classic` (dev checkout typically `/src/forge-classic`, deployed `/var/local/forge-classic`)
and its theme `sftheme` (`/src/sftheme`, `/var/local/sftheme`). This repo has zero references back to
either — the dependency runs one-way, entirely through the entry-point mechanism described below. See
"Working with sibling extension repos" further down for how to debug across that boundary.

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

## Development patterns

- **Adding a new tool**: subclass `allura.app.Application`, then register it under
  `[project.entry-points.allura]` in that package's `pyproject.toml` (e.g. `Tickets =
  "forgetracker.tracker_main:ForgeTrackerApp"`). Code alone doesn't register a tool — without the entry
  point, `g.entry_points['tool']` never sees it (see `Allura/allura/lib/app_globals.py:346-352`) and it
  won't be mountable, won't appear in the admin "add tool" list, etc.
- **Adding a Markdown macro**: decorate a function with `@macro()` from `allura.lib.macro`, register it
  under `[project.entry-points."allura.macros"]`. The entry point *name* is arbitrary; the macro is
  invoked in Markdown by the function's own name (`[[hello]]`). See
  `Allura/docs/development/extending.rst` for the full list of extension points (auth providers, theme
  providers, spam filters, phone services, WSGI middleware, webhooks, `allura.timers`, etc.) — most
  follow this same "subclass + entry point" shape.
- **Resolving duplicate entry-point names**: if two installed packages register the same name under an
  `allura`/`allura.*` group (e.g. a sibling repo overriding a stock tool), `iter_entry_points`
  (`Allura/allura/lib/helpers.py:1193-1237`) requires one registered class to be a subclass of the
  other(s); otherwise it raises `ImportError('Ambiguous ... entry points ...')` at the point something
  tries to use that group. When subclassing another tool specifically to reuse its entry-point name,
  make sure the inheritance is real (not just structurally similar).
- **Disabling an entry point without removing the package**: `disable_entry_points.<group> = name1,
  name2` in the `.ini` (see examples in `Allura/development.ini:519-525`, e.g.
  `disable_entry_points.allura.importers = trac-tickets`). Useful for turning off a stock or
  third-party plugin at config time instead of uninstalling it.
- **Context helpers for scripts/tests**: `allura.lib.helpers.set_context(project_id, mount_point=...,
  app_config_id=..., neighborhood=...)` sets `c.project`/`c.app` outside normal request dispatch; the
  `push_config(obj, **kw)` context manager temporarily overrides attributes on any object (e.g. `c`, `g`,
  a model instance) and restores them on exit — prefer it over manual save/restore boilerplate in tests
  and scripts.
- **Migration scripts** (`scripts/migrations/`): numbered `NNN-description.{py,js,sh}` files, run once
  against a real environment and not re-run automatically — there's no migration-runner/version table,
  just sequential numbering as a changelog. `.js` files are raw `mongo`/`mongosh` scripts; `.py`/`.sh`
  ones are typically invoked via `paster script <ini> <script.py> -- <args>` (see "Debugging" below).
  Field-conversion migrations often come in pairs — a `-field-encryption.sh`-style script that converts
  values, and a later `...-cleanup.sh` companion that removes the old unencrypted copies once the
  conversion is verified (e.g. `scripts/migrations/037-field-encryption.sh` /
  `038-field-encryption-cleanup.sh`, both thin wrappers around
  `scripts/convert_encrypted_field.py`). Follow that shape (convert now, clean up in a later,
  separately-run script) for any similarly risky data migration.

## Debugging

- **Tracing a request**: dispatch for every request starts in
  `Allura/allura/controllers/root.py`. If the request is handled by a tool, find the tool's entry point
  under `[project.entry-points.allura]` in its `pyproject.toml`/`setup.py`, load the `Application`
  subclass it points to, and follow its `root` attribute — that's the tool's root controller. Failing
  that, grep for static text from the rendered page's HTML, or the template filename once you find it.
  (`Allura/docs/development/contributing.rst` has more detail.)
- **Interactive debugging (`ipdb`)**: insert `import ipdb; ipdb.set_trace()` at the line of interest,
  then run the relevant process in the foreground so the debugger has a console to attach to:
  ```bash
  cd Allura
  pkill -f gunicorn; gunicorn --reload --paste development.ini -b :8080      # web
  pkill -f taskd; paster taskd development.ini --nocapture                    # taskd
  ```
  Docker equivalent:
  ```bash
  docker compose run --rm web pip install ipdb
  docker compose stop web taskd
  docker compose run --rm --service-ports web gunicorn --reload --paste Allura/docker-dev.ini -b :8088
  docker compose run --rm taskd paster taskd docker-dev.ini --nocapture
  ```
- **One-off scripts**: `paster script <ini> <script.py> -- <args>` (implemented by
  `allura.command.script:ScriptCommand`, registered under `[project.entry-points."paste.paster_command"]`
  in `Allura/pyproject.toml`) loads the full app config (DB bindings, TG globals, logging) and executes
  the script inside that context — no serving loop. Add `--pdb` to drop into `pdb.post_mortem()` on an
  uncaught exception instead of just printing a traceback.
- **Entry points silently not registering**: `Globals.__init__` caches every entry-point group once, per
  process, into `g.entry_points` (`Allura/allura/lib/app_globals.py:328-338`, `_cache_eps`) — and that
  cache function swallows exceptions from a failed `ep.load()`, only logging `Could not load entry
  point [%s] %s` (`resources.py` similarly logs `Cannot import entry point %s` for static-resource
  registration). If a class you expect to see registered (your own, or a sibling package's) isn't
  showing up in `g.entry_points[...]`, check the web/taskd process logs for those messages before
  assuming the entry point declaration itself is wrong — an import error inside the target module fails
  silently from the caller's perspective. Also remember `g` is built once at process startup
  (`Allura/allura/lib/app_globals.py:212-217`): adding/editing an entry point (even via `pip install -e`)
  needs a process restart, a code *reload* (`--reload`) is not enough. Escalating checks, from
  outside-in:
  ```bash
  # 1. is it discoverable at all, independent of Allura's own filtering?
  python -c "import importlib.metadata as m; [print(ep) for ep in m.entry_points(group='allura.theme.override')]"
  ```
  ```python
  # 2. is Allura's own loader (dedup/subclass/disable filtering) seeing it? run inside
  #    `paster script development.ini <tmp_script.py>` (see docs/getting_started/administration.rst)
  from allura.lib import helpers as h
  list(h.iter_entry_points('allura.theme.override'))
  list(h.iter_entry_points('allura.admin'))
  # or inspect the live cache directly:
  import tg; tg.app_globals.entry_points['admin']
  ```
  There's no `paster shell`/REPL command registered in this stack for ad hoc poking — use a throwaway
  script under `Allura/scripts/` with `paster script` instead.

## Working with sibling extension repos (forge-classic, sftheme)

`forge-classic` layers SourceForge-specific tools, overrides, and business logic on top of this Allura
checkout purely via the entry-point mechanisms above — see its own `CLAUDE.md` for what it registers.
From this side, a few things make debugging across that boundary easier:

- **Template overrides**: a sibling package's `override/` directory (e.g. forge-classic's
  `ForgeSF/forgesf/override/`) is spliced into the Jinja search path by
  `allura.lib.package_path_loader.PackagePathLoader`, driven by that package's
  `[project.entry-points."allura.theme.override"]` registration. Default resolution order puts each
  override just before the stock `allura` path (`_load_paths`,
  `Allura/allura/lib/package_path_loader.py:162-174`); a package can reorder itself relative to another
  override or to `allura` via a `template_path_rules = [['>', 'other-ep-name']]` class attribute
  (`>`/`<`/`=`, see the module docstring at the top of that file for the full rule syntax). If a page
  doesn't reflect an expected override, set `disable_template_overrides = true` in the `.ini` temporarily
  to confirm what stock Allura renders, then check `template_path_rules`/override ordering rather than
  assuming the template content itself is wrong. To see the actual resolved search order (which
  directory wins), instantiate the loader directly in a `paster script`:
  ```python
  from allura.lib.package_path_loader import PackagePathLoader
  PackagePathLoader().init_paths()   # ordered list of override dirs actually being searched
  ```
  A common failure is the physical directory being nested one level off — the convention is
  `override/<top-level-package-of-the-module>/templates/...` (see the "magic directory" example in
  `package_path_loader.py`'s module docstring), not `override/<full.dotted.module>/...`.
- **Non-template overrides are monkeypatches, not templates**: some `override/` files are plain Python
  that reassigns methods/attributes directly onto imported Allura classes at import time (forge-classic's
  `repo_monkey_patching.py`, imported eagerly from its package `__init__.py`, is one example). If
  behavior differs from what this repo's source implies, grep the sibling package for the Allura
  class/method name before assuming you're looking at stock behavior — check whether the specific
  override file in question is a template or a patch, since the two mechanisms are unrelated. Allura's
  own idiomatic monkeypatch shape is `allura.lib.helpers.monkeypatch(*objs)` (used internally in
  `allura/lib/patches.py`), which only takes effect once its module is actually imported — if a
  sibling-package patch isn't applying, confirm its module is really being imported (e.g. as a side
  effect of package `__init__.py`, or of an `allura.command_init`/`allura.macros` entry-point load) before
  assuming the patch logic itself is wrong.
- **Shared MongoDB, independently resolved dependencies**: sibling repos typically point at the *same*
  physical Mongo (so a data bug can originate in either codebase's model layer — check both), but each
  repo's `requirements.txt` is compiled independently, so their installed dependency versions can drift
  even when both declare the same package. A sibling repo's test config often extends this repo's
  `Allura/test.ini` via ConfigParser's `use = config:...` inheritance — when a test only fails in the
  sibling repo, diff the two `.ini` files to see what's inherited vs. locally overridden before assuming
  it's a real behavioral difference.
- **Ambiguous/duplicate entry-point names across repos** hit the same `iter_entry_points` subclass
  check described above — a sibling package overriding a stock tool/app under the same entry-point name
  must genuinely subclass it, or loading that group raises `ImportError` at runtime.

## Miscellaneous conventions

- Timezone safety: always use UTC-explicit datetime functions (see Linting section above) — this is enforced
  by pre-commit and `test_syntax.py`, not by ruff itself.
- License headers: nearly every source file carries an ASF license header; `rat-excludes.txt` lists what's
  exempt. Keep new files consistent with neighboring files' headers.
- Sensitive fields (e.g. user email) may be stored with field-level encryption — see
  `Allura/allura/model/auth.py` and `scripts/convert_encrypted_field.py` for the pattern used when adding new
  encrypted fields.
