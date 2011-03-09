Third-party Data Migration
==========================

Allura provides means to migrate existing project data hosted in other applications.
At this time, tracker/ticket import is available. The migration procedure is as follows:

1. Export data from your application into ForgePlucker JSON-based interchanged format
   (http://home.gna.org/forgeplucker/forge-ontology.html).
2. Prepare a tracker in Allura project for import.
3. Validate import data.
4. Request Import API Ticket.
5. Perform actual migration.

Subsection below discuss each step in more detail.

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
account on SourceForge, but it is usually more important to make sure that
assigned-to users do have. Assigned-to users are usually more closed set, like
members of your project, so it's good idea to ask them to register SF.net account
before performing import.

Another common issue is that username in original tracker and in SF.net do not
match. Import service provides ability to specify user mapping to overcome this.
For example, you can specify that user "john" as appearing in JSON should be
translated to "john2" in SF.net. Mapping should be prepared in the form of JSON
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

Performing actual import
------------------------
To perform actual import, you should request an import API ticket. This is done
via the usual support channel for SourceForge.net, please refer to site
documentation. You should submit a ticket with details of the project you want
to import to, and description of why and from what source you want to perform
migration. After due diligence check, support admins will issue an API ticket/
secret pair. This pair can be used the same way as API key/secret key. But unlike
API key, the ticket has expiration date, and is usually valid for use only within
24-48 hours.

The same script ``allura_import.py``, is used for actual import, you just should
omit ``--validation`` option and use API ticket/secret pair::

 python allura_import.py -u http://sourceforge.net \
   -a <API ticket> -s <ticket secret>
   -p test -t bugs \
   --user-map=users.json \
   import.json
