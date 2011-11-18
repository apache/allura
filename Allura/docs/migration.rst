Third-party Data Migration
==========================

Allura provides means to migrate existing project data hosted in other applications.
At this time, tracker/ticket import is available. The migration procedure is as follows:

1. Export data from your application into ForgePlucker JSON-based interchanged format
   (http://home.gna.org/forgeplucker/forge-ontology.html).
2. Prepare a tracker in Allura project for import.
3. Validate import data.
4. Request/Generate Import API Ticket.
5. Perform actual migration.

Subsections below discuss each step in more detail.

Exporting data
--------------
The aim of migration services in Allura was to support various applications and
data tools. This is achieved by using intermediate format to represent data which
were exported from 3rd-party application and will be imported into Allura. This
formated is based on proposals of ForgePlucker project (http://home.gna.org/forgeplucker/)
and is relatively simple JSON-based format. Please note that there some differences
to the format as described in ForgePlucker documents, because ForgePlucker format
is itself not finalized, and there was need to tweak format based on actual usecases
with Allura. There is currently no standalone description of format understood
by Allura, output produced by sample exporter(s) provided should be taken as the
reference.

At this time, only single-tracker imports are supported.

There is a proof-of-concept Trac exporter provided. It is expected that it will be
elaborated, and more exporters written on as-needed basis, both by Allura developers
and community. We will be glad to integrate any useful contributions.

Preparing for import
--------------------
Allura strives to provide as faithful and lossless import as possible. However,
to achieve this, some help from user is required. The most important part of it
is ensuring that users referenced in the import JSON are available in Allura.
If, during import, some user does not exist, corresponding field in a ticket will
be set to Nobody/Anonymous.

It oftentimes not possible or plausible to ensure that all submitting users have
account on the forge, but it is usually more important to make sure that
assigned-to users do. Assigned-to users are usually a smaller set, like
members of your project, so it's good idea to ask them to register an account
before performing import.

Another common issue is that username in original tracker and in the forge do not
match. The import service provides the ability to specify user mapping to overcome this.
For example, you can specify that user "john" as appearing in JSON should be
translated to "john2" in the forge. Mapping should be prepared in the form of JSON
dictionary, e.g. ``{"john": "john2"}``.

Other issue is extra ticket fields appearing in the original tracker. Allura
tracker by default support small number of generally usable fields. More fields
can be created as "custom" ones. Import service has the to automatically create
custom fields for unknown fields appearing in import JSON. However, it will use
"string" type for them. If that's not what you want, you should pre-create all
custom fields in the custom tracker with correct types.


Validating import data
----------------------
Before you do actual import, it makes sense to perform "dry run" import to
catch any issues. This is especially true as real import requires special
permission granted by an "API ticket" (more on this below).

Both validating and actual import is executed using a REST API call. There's
however a script provided which takes command-line arguments, pre-processes
them and executes need REST API call. This script is called ``allura_import.py``.
To run it in the validation mode::

 python allura_import.py -u http://sourceforge.net \
   -a <API key> -s <Secret key>
   -p test -t bugs \
   --user-map=users.json \
   --validate import.json


Getting Import API ticket
-------------------------
To perform actual import, you should request an Import API ticket from site
administrator. For user-facing documentation for SourceForge.net, please refer
to the corresponding section at https://sourceforge.net/p/forge/documentation/ToC/ .

Below are described site admin's step to generate an API ticket on user's request.

Visit /nf/admin/ link of the site for Site Admin pages. Select "API Tickets" from
left navigation menu. There will be a form to generate a new ticket and a list of
existing API tickets (most recently generated first) below it. To create a ticket,
fill in following information:

* Username - all actions performed using the ticket will be tied to this account.
* Capabilities (JSON) - all API tickets must have capabilities (represented with
  JSON dictionary) set. For import, this should be ``{"import": [<nbhd_name>, <project_shortname>}``,
  e.g. ``{"import": ["Projects", "test"]}``. For multiple projects, several tickets must be created.
* Expiration date - All API tickets are time-limited, with default active duration
  of 48 hours, all actions using the ticket must be performed within this timeframe.

Once a ticket is generated (will be shown topmost in the list), API ticket and secret
key values must be passed securely to the requesting user.


Performing actual import
------------------------
The same script ``allura_import.py``, is used for actual import, you just should
omit ``--validation`` option and use API ticket/secret pair::

 python allura_import.py -u http://sourceforge.net \
   -a <API ticket> -s <ticket secret>
   -p test -t bugs \
   --user-map=users.json \
   import.json
