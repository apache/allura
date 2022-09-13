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

"""The application's model objects"""

from .neighborhood import Neighborhood, NeighborhoodFile
from .project import Project, ProjectCategory, TroveCategory, ProjectFile, AppConfig
from .index import ArtifactReference, Shortlink
from .artifact import Artifact, MovedArtifact, Message, VersionedArtifact, Snapshot, Feed, AwardFile, Award, AwardGrant
from .artifact import VotableArtifact
from .discuss import Discussion, Thread, PostHistory, Post, DiscussionAttachment
from .attachments import BaseAttachment
from .auth import AuthGlobals, User, ProjectRole, EmailAddress
from .auth import AuditLog, AlluraUserProperty, UserLoginDetails
from .filesystem import File
from .notification import Notification, Mailbox, SiteNotification
from .repository import Repository, RepositoryImplementation, CommitStatus
from .repository import MergeRequest, GitLikeTree
from .stats import Stats
from .oauth import OAuthToken, OAuthConsumerToken, OAuthRequestToken, OAuthAccessToken
from .monq_model import MonQTask
from .webhook import Webhook
from .multifactor import TotpKey

from .types import ACE, ACL, EVERYONE, ALL_PERMISSIONS, DENY_ALL, MarkdownCache
from .session import main_doc_session, main_orm_session, main_explicitflush_orm_session
from .session import project_doc_session, project_orm_session
from .session import artifact_orm_session, repository_orm_session
from .session import task_orm_session
from .session import ArtifactSessionExtension

from . import repository
from . import repo_refresh

from ming.orm import Mapper
Mapper.compile_all()

__all__ = [
    'Neighborhood', 'NeighborhoodFile', 'Project', 'ProjectCategory', 'TroveCategory', 'ProjectFile', 'AppConfig',
    'ArtifactReference', 'Shortlink', 'Artifact', 'MovedArtifact', 'Message', 'VersionedArtifact', 'Snapshot', 'Feed',
    'AwardFile', 'Award', 'AwardGrant', 'VotableArtifact', 'Discussion', 'Thread', 'PostHistory', 'Post',
    'DiscussionAttachment', 'BaseAttachment', 'AuthGlobals', 'User', 'ProjectRole', 'EmailAddress',
    'AuditLog', 'AlluraUserProperty', 'File', 'Notification', 'Mailbox', 'Repository',
    'RepositoryImplementation', 'CommitStatus', 'MergeRequest', 'GitLikeTree', 'Stats', 'OAuthToken', 'OAuthConsumerToken',
    'OAuthRequestToken', 'OAuthAccessToken', 'MonQTask', 'Webhook', 'ACE', 'ACL', 'EVERYONE', 'ALL_PERMISSIONS',
    'DENY_ALL', 'MarkdownCache', 'main_doc_session', 'main_orm_session', 'project_doc_session', 'project_orm_session',
    'artifact_orm_session', 'repository_orm_session', 'task_orm_session', 'ArtifactSessionExtension', 'repository',
    'repo_refresh', 'SiteNotification', 'TotpKey', 'UserLoginDetails', 'main_explicitflush_orm_session']
