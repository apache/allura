#!/bin/bash

# Install RPMs.
yum install -y python-devel
yum install -y openldap-devel

./setup-common.bash
