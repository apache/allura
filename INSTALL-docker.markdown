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

# General info

## Allura runs on following docker containers:

- web
- mongo
- taskd
- solr
- inmail
- outmail

## Host-mounted volumes (created on first run)

Current directory mounted as `/allura` inside containers.

Python environment:

- `env-docker/python`
- `env-docker/bin`

Services data:

- `/allura-data/mongo` - mongo data
- `/allura-data/solr` - SOLR index
- `/allura-data/scm/{git,hg,svn}` - code repositories
- `/allura-data/scm/snapshots` - generated code snapshots

## Ports, exposed to host system:

- 8080 - webapp
- 8983 - SOLR admin panel (http://localhost:8983/solr/)
- 8825 - incoming mail listener


# First run

[Download the latest release](http://www.apache.org/dyn/closer.cgi/allura/) of Allura, or [clone from git](https://forge-allura.apache.org/p/allura/git/ci/master/tree/) for the bleeding edge.

Install [Docker](http://docs.docker.com/installation/) and [Docker Compose](https://docs.docker.com/compose/install/).

Build/fetch all required images (run these in your allura directory):

    ~$ docker-compose build

Install requirements:

    ~$ docker-compose run web pip install -r requirements.txt

Install Allura packages:

    ~$ docker-compose run web ./rebuild-all.bash

Initialize database with test data:

    ~$ docker-compose run web bash -c 'cd Allura && paster setup-app docker-dev.ini'

If you want to skip test data creation you can instead run:

    ~$ docker-compose run web bash -c 'cd Allura && ALLURA_TEST_DATA=False paster setup-app docker-dev.ini'

Start containers in background:

    ~$ docker-compose up -d

# Useful commands

Restarting all containers:

    ~$ docker-compose up -d

View logs from all services:

    ~$ docker-compose logs

You can specify one or more services to view logs only from them, e.g. to see
outgoing mail:

    ~$ docker-compose logs outmail

Update requirements and reinstall apps:

    ~$ docker-compose run web pip install -r requirements.txt
    ~$ docker-compose run web ./rebuild-all.bash

You may want to restart at least taskd container after that in order for it to
pick up changes.

Running all tests:

    ~$ docker-compose run web ./run_tests

Running subset of tests:

    ~$ docker-compose run web bash -c 'cd ForgeGit && nosetests forgegit.tests.functional.test_controllers:TestFork'

Connecting to mongo directly:

    ~$ docker-compose run mongo mongo --host mongo
