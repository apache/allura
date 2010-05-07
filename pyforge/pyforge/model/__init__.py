# -*- coding: utf-8 -*-
"""The application's model objects"""

from .session import ProjectSession
from .project import Theme, Neighborhood, NeighborhoodFile, Project, ProjectCategory, ProjectFile, AppConfig, SearchConfig, ScheduledMessage
from .discuss import Discussion, Thread, PostHistory, Post, Attachment
from .artifact import Artifact, Message, VersionedArtifact, Snapshot, ArtifactLink, Feed, AwardFile, Award, AwardGrant
from .auth import User, ProjectRole, OpenId, EmailAddress, ApiToken
from .openid_model import OpenIdStore, OpenIdAssociation, OpenIdNonce
from .filesystem import File
from .tag import TagEvent, Tag, UserTags
from .notification import Notification, Subscriptions, Mailbox
from .repository import Repository, Commit

from .types import ArtifactReference, ArtifactReferenceType

from .session import main_doc_session, main_orm_session
from .session import project_doc_session, project_orm_session
from .session import artifact_orm_session

from ming.orm.mapped_class import MappedClass
MappedClass.compile_all()
