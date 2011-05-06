# -*- coding: utf-8 -*-
"""The application's model objects"""

from .neighborhood import Neighborhood, NeighborhoodFile
from .project import Project, ProjectCategory, TroveCategory, ProjectFile, AppConfig
from .index import ArtifactReference, Shortlink
from .artifact import Artifact, Message, VersionedArtifact, Snapshot, Feed, AwardFile, Award, AwardGrant
from .discuss import Discussion, Thread, PostHistory, Post, DiscussionAttachment
from .attachments import BaseAttachment
from .auth import AuthGlobals, User, ProjectRole, OpenId, EmailAddress, ApiToken, ApiTicket, OldProjectRole
from .openid_model import OpenIdStore, OpenIdAssociation, OpenIdNonce
from .filesystem import File
from .notification import Notification, Mailbox
from .repository import Repository, RepositoryImplementation, RepoObject, Commit, Tree, Blob
from .repository import LogCache, LastCommitFor, MergeRequest, GitLikeTree
from .stats import Stats, CPA
from .oauth import OAuthToken, OAuthConsumerToken, OAuthRequestToken, OAuthAccessToken
from .monq_model import MonQTask

from .types import ACE, ACL, EVERYONE, ALL_PERMISSIONS, DENY_ALL
from .session import main_doc_session, main_orm_session
from .session import project_doc_session, project_orm_session
from .session import artifact_orm_session, repository_orm_session

from ming.orm import Mapper
Mapper.compile_all()
