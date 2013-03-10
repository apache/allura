from datetime import datetime

import iso8601
import pymongo
import pylons
pylons.c = pylons.tmpl_context
pylons.g = pylons.app_globals
from pylons import c, g

import bson
from ming import schema as S
from ming import Field, Index, collection
from ming.orm import session, state, Mapper
from ming.orm import FieldProperty, RelationProperty, ForeignIdProperty
from ming.orm.declarative import MappedClass

import allura.tasks.mail_tasks
from allura.lib import helpers as h
from allura.lib import plugin

from allura.model.session import main_orm_session

from allura.model import User
import allura.model as M

class Organization(MappedClass):
    class __mongometa__:
        name='organization'
        session = main_orm_session
        unique_indexes = [ 'shortname' ]

    _id=FieldProperty(S.ObjectId)
    shortname=FieldProperty(str)
    fullname=FieldProperty(str)
    organization_type=FieldProperty(S.OneOf(
        'For-profit business',
        'Foundation or other non-profit organization',
        'Research and/or education institution'))
    description=FieldProperty(str)
    headquarters=FieldProperty(str)
    dimension=FieldProperty(
        S.OneOf('Small', 'Medium', 'Large', 'Unknown'),
        if_missing = 'Unknown')
    website=FieldProperty(str)
    workfields=FieldProperty([S.ObjectId])
    created=FieldProperty(S.DateTime, if_missing=datetime.utcnow())
    
    memberships=RelationProperty('Membership')
    project_involvements=RelationProperty('ProjectInvolvement')

    def url(self):
        return ('/o/' + self.shortname.replace('_', '-') + '/').encode('ascii','ignore')

    def project(self):
        return M.Project.query.get(
            shortname='o/'+self.shortname.replace('_', '-'))

    @classmethod
    def register(cls, shortname, fullname, orgtype, user):
        o=cls.query.get(shortname=shortname)
        if o is not None: return None
        try:
            o = cls(
                shortname=shortname, 
                fullname=fullname,
                organization_type=orgtype)
            session(o).flush(o)
        except pymongo.errors.DuplicateKeyError:
            session(o).expunge(o)
            return None
        if o is not None:
            n = M.Neighborhood.query.get(name='Organizations')
            n.register_project('o/'+shortname, user=user, user_project=False)
        return o

    @classmethod
    def delete(cls, o):
        try:
            session(o).expunge(o)
        except:
            return False
        return True

    @classmethod
    def getById(cls, org_id):
        org_id = str(org_id)
        org_id = bson.ObjectId(org_id)
        return cls.query.get(_id=org_id)

    def getWorkfields(self):
        l = []
        for wf in self.workfields:
            l.append(WorkFields.query.get(_id = wf))
        return l

    def addWorkField(self, workfield):
        wfid = workfield._id
        if not wfid in self.workfields:
            self.workfields.append(wfid)
           
    def removeWorkField(self, workfield):
        wfid = workfield._id
        if wfid in self.workfields:
            del self.workfields[self.workfields.index(wfid)]

    def getActiveCooperations(self):
        return [c for c in self.project_involvements if c.status=='active' and
            c.collaborationtype == 'cooperation']

    def getPastCooperations(self):
        return [c for c in self.project_involvements if c.status=='closed' and 
            c.collaborationtype == 'cooperation']

    def getActiveParticipations(self):
        return [c for c in self.project_involvements if c.status=='active' and 
            c.collaborationtype == 'participation']

    def getPastParticipations(self):
        return [c for c in self.project_involvements if c.status=='closed' and 
            c.collaborationtype == 'participation']

    def getEnrolledUsers(self):
        return [m for m in self.memberships if m.status=='active']

class WorkFields(MappedClass):
    class __mongometa__:
        session = main_orm_session
        name='work_fields'

    _id=FieldProperty(S.ObjectId)
    name=FieldProperty(str)
    description=FieldProperty(str, if_missing='')

    @classmethod
    def insert(cls, name, description):
        wf=cls.query.get(name=name)
        if wf is not None: 
            return None
        try:
            wf = cls(name=name, description=description)
            session(wf).flush(wf)
        except pymongo.errors.DuplicateKeyError:
            session(wf).expunge(wf)
            return None
        return wf

    @classmethod
    def getById(cls, workfieldid):
        workfieldid = str(workfieldid)
        workfieldid = bson.ObjectId(workfieldid)
        return cls.query.get(_id=workfieldid)

class Membership(MappedClass):
    class __mongometa__:
        session = main_orm_session
        name='organization_membership'

    _id=FieldProperty(S.ObjectId)
    status=FieldProperty(S.OneOf('active', 'closed', 'invitation', 'request'))
    role=FieldProperty(str)
    organization_id=ForeignIdProperty('Organization')
    member_id=ForeignIdProperty('User')
    startdate = FieldProperty(S.DateTime, if_missing=None)
    closeddate = FieldProperty(S.DateTime, if_missing=None)

    organization = RelationProperty('Organization')
    member = RelationProperty('User')

    @classmethod
    def insert(cls, role, status, organization_id, member_id):
        m = cls.query.find(dict(organization_id=organization_id, member_id=member_id))
        for el in m:
            if el.status!='closed':
                return None
        try:
            m = cls(
                organization_id=organization_id, 
                member_id=member_id,
                role=role,
                startdate=None,
                status=status)
            session(m).flush(m)
        except pymongo.errors.DuplicateKeyError:
            session(m).expunge(m)
            m = cls.query.get(organization_id=organization_id, member_id=member_id)
        if status == 'active':
            m.startdate = datetime.utcnow()

        return m
    
    @classmethod
    def delete(cls, membership):
        cls.query.remove(dict(_id=membership._id))
        
    @classmethod
    def getById(cls, membershipid):
        membershipid = str(membershipid)
        membershipid = bson.ObjectId(membershipid)
        return cls.query.get(_id=membershipid)

    def setStatus(self, status):
        if status=='active' and self.status!='active':
            self.startdate = datetime.utcnow()
        elif status=='closed':
            self.closeddate = datetime.utcnow()
        self.status = status

class ProjectInvolvement(MappedClass):
    class __mongometa__:
        session = main_orm_session
        name='project_involvement'

    _id=FieldProperty(S.ObjectId)
    status=FieldProperty(S.OneOf('active', 'closed', 'invitation', 'request'))
    collaborationtype=FieldProperty(S.OneOf('cooperation', 'participation'))
    organization_id=ForeignIdProperty('Organization')
    project_id=ForeignIdProperty('Project')
    startdate = FieldProperty(S.DateTime, if_missing=None)
    closeddate = FieldProperty(S.DateTime, if_missing=None)

    organization = RelationProperty('Organization')
    project = RelationProperty('Project')
    
    @classmethod
    def insert(cls, status, collaborationtype, organization_id, project_id):
        p = cls.query.find(dict(
            organization_id=organization_id, 
            project_id=project_id))
        for el in p:
            if p.status != 'closed':
                return None
        try:
            m = cls(organization_id=organization_id, project_id=project_id, status=status, collaborationtype=collaborationtype)
            session(m).flush(m)
        except pymongo.errors.DuplicateKeyError:
            session(m).expunge(m)
            m = cls.query.get(organization_id=organization_id, project_id=project_id)
        return m
    
    @classmethod
    def delete(cls, coll_id):
        cls.query.remove(dict(_id=coll_id))

    @classmethod
    def getById(cls, p_id):
        p_id = str(p_id)
        p_id = bson.ObjectId(p_id)
        return cls.query.get(_id=p_id)

    def setStatus(self, status):
        if status=='active' and self.status!='active':
            self.startdate = datetime.utcnow()
        elif status=='closed':
            self.closeddate = datetime.utcnow()
        self.status = status

Mapper.compile_all()
