# -*- coding: utf-8 -*-
"""The application's model objects"""

from .session import ProjectSession

from .neighborhood import Neighborhood, NeighborhoodFile
from .project import Project, ProjectCategory, ProjectFile, AppConfig, SearchConfig, ScheduledMessage
from .index import ArtifactReference, Shortlink, IndexOp
from .artifact import Artifact, Message, VersionedArtifact, Snapshot, Feed, AwardFile, Award, AwardGrant
from .discuss import Discussion, Thread, PostHistory, Post, DiscussionAttachment
from .attachments import BaseAttachment
from .auth import AuthGlobals, User, ProjectRole, OpenId, EmailAddress, ApiToken, ApiTicket, OldProjectRole
from .openid_model import OpenIdStore, OpenIdAssociation, OpenIdNonce
from .filesystem import File
from .notification import Notification, Mailbox
from .repository import Repository, RepositoryImplementation, RepoObject, Commit, Tree, Blob
from .repository import LogCache, LastCommitFor, MergeRequest
from .stats import Stats, CPA
from .import_batch import ImportBatch
from .oauth import OAuthToken, OAuthConsumerToken, OAuthRequestToken, OAuthAccessToken
from .monq_model import MonQTask

from .types import ArtifactReference, ArtifactReferenceType

from .session import main_doc_session, main_orm_session
from .session import project_doc_session, project_orm_session
from .session import artifact_orm_session, repository_orm_session

from ming.orm import MappedClass
MappedClass.compile_all()
