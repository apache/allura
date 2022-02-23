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

'''This class is supposed to be extended in order to support statistics for
a specific entity (e.g. user, project, ...). To do so, the new classes should
overwrite the methods defined here, which will be called when the related
event happens, so that the statistics for the given entity are updated.'''


class EventsListener:

    def newArtifact(self, art_type, art_datetime, project, user):
        pass

    def modifiedArtifact(self, art_type, art_datetime, project, user):
        pass

    def newUser(self, user):
        pass

    def newOrganization(self, organization):
        pass

    def addUserLogin(self, user):
        pass

    def newCommit(self, newcommit, project, user):
        pass

    def ticketEvent(self, event_type, ticket, project, user):
        pass

    def addUserToOrganization(self, newMembership):
        pass

'''This class simply allows to iterate through all the registered listeners,
so that all of them are called to update statistics.'''


class PostEvent:

    def __init__(self, listeners):
        self.listeners = listeners

    def __iterate(self, event, *d):
        for l in self.listeners:
            getattr(l, event)(*d)

    def newArtifact(self, art_type, art_datetime, project, user):
        self.__iterate('newArtifact', art_type, art_datetime, project, user)

    def modifiedArtifact(self, art_type, art_datetime, project, user):
        self.__iterate('modifiedArtifact', art_type,
                       art_datetime, project, user)

    def newUser(self, user):
        self.__iterate('newUser', user)

    def newOrganization(self, organization):
        self.__iterate('newOrganization', organization)

    def addUserLogin(self, user):
        self.__iterate('addUserLogin', user)

    def newCommit(self, newcommit, project, user):
        self.__iterate('newCommit', newcommit, project, user)

    def ticketEvent(self, event_type, ticket, project, user):
        self.__iterate('ticketEvent', event_type, ticket, project, user)

    def addUserToOrganization(self, organization):
        self.__iterate('addUserToOrganization', organization)
