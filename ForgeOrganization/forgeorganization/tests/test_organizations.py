import pkg_resources
import unittest

from pylons import app_globals as g
from pylons import tmpl_context as c
from ming.orm.ormsession import ThreadLocalORMSession, session

from alluratest.controller import TestController, setup_basic_test, setup_global_objects
from allura.tests import decorators as td
from allura.lib import helpers as h
from allura.model import User
from allura import model as M

from forgegit.tests import with_git
from forgeorganization.organization import model as OM
import tg

class TestOrganization(TestController):

    def setUp(self):
        setup_basic_test(config='test.ini')
        setup_global_objects()
        super(TestOrganization, self).setUp()

        c.user = User.by_username('test-user-1')
        #Create a test organization
        self.name = 'testorg'
        self.fullname = 'Test Organization'
        self.role = 'Developer'
        self.orgtype = 'Foundation or other non-profit organization'
        r = self.app.post('/organization/save_new/', 
            params=dict(
                fullname=self.fullname,
                shortname=self.name,
                orgtype=self.orgtype,
                role=self.role),
            extra_environ=dict(username='test-user-1'))

        self.org = OM.Organization.query.get(shortname=self.name)

        #Add a new user
        self.user2 = User.by_username('test-user-2')
        r = self.app.post('/organization/%s/invite_user' % self.name,
            params=dict(
                username = self.user2.username,
                role = 'Software Engineer'),
            extra_environ=dict(username='test-user-1'))
        m = OM.Membership.query.get(
            member_id=self.user2._id, 
            organization_id=self.org._id)
        r = self.app.post('/organization/%s/change_membership' % self.name,
            params=dict(
                status = 'active',
                permission = 'member',
                membershipid = str(m._id),
                requestfrom = 'user',
                role = 'Software Engineer'),
            extra_environ=dict(username='test-user-2'))

class TestOrganizationGeneral(TestOrganization):

    @td.with_user_project('test-user-1')
    def test_registration(self):
        #Test organization registration
        r = self.app.get('/organization/',
            extra_environ=dict(username='test-user-1'))
        assert 'Test Organization' in r
        org = OM.Organization.query.get(shortname=self.name)
        assert self.org.fullname == self.fullname
        assert self.org.organization_type == self.orgtype

        #Check that the user is the administrator of the org. profile
        m = OM.Membership.query.get(
            member_id=c.user._id,
            organization_id=self.org._id)
        assert self.org.userPermissions(c.user) == 'admin'
        assert m.status == 'active'
        assert m.role == self.role

    @td.with_user_project('test-user-1')
    def test_update_profile(self):

        fullname = 'New Full Name'
        organization_type = 'For-profit business'
        description = 'New test description'
        dimension = 'Medium'
        headquarters = 'Milan'
        website = 'http://www.example.com'

        #Update the profile of the organization
        r = self.app.post('/organization/%s/change_data' % self.name,
            params = dict(
                fullname = fullname,
                organization_type = organization_type,
                description = description,
                dimension = dimension,
                headquarters = headquarters,
                website = website),
            extra_environ=dict(username='test-user-1'))

        ThreadLocalORMSession.flush_all()

        r = self.app.get('/organization/%s/' % self.name)
        assert organization_type in r
        assert description in r
        assert headquarters in r
        assert fullname in r
        assert website in r

        self.org = OM.Organization.query.get(_id=self.org._id)

        assert self.org.organization_type == organization_type
        assert self.org.description == description
        assert self.org.dimension == dimension
        assert self.org.headquarters == headquarters
        assert self.org.website == website
        assert self.org.fullname == fullname

        #Try to provide invalid parameters
        r = self.app.post('/organization/%s/change_data' % self.name,
            params = dict(
                fullname = 'a',
                organization_type = 'Invalid type',
                description = 'b',
                dimension = 'Invalid dimension',
                headquarters = 'c',
                website = 'd'),
            extra_environ=dict(username='test-user-1'))

        ThreadLocalORMSession.flush_all()

        r = self.app.get('/organization/%s/' % self.name,
            extra_environ=dict(username='test-user-1'))

        self.org = OM.Organization.query.get(_id=self.org._id)
        assert self.org.organization_type == organization_type
        assert self.org.description == description
        assert self.org.dimension == dimension
        assert self.org.headquarters == headquarters
        assert self.org.website == website
        assert self.org.fullname == fullname

    @td.with_user_project('test-user-1')
    def test_workfield(self):

        wf = OM.WorkFields.query.get(name='Mobile apps')
        c.user = User.by_username('test-user-1')

        r = self.app.get('/organization/%s/edit_profile' % self.name)

        #Add a workfield
        r = self.app.post('/organization/%s/add_work_field' % self.name,
            params = dict(
                workfield = str(wf._id)),
            extra_environ=dict(username='test-user-1'))

        r = self.app.get('/organization/%s/' % self.name)
        
        self.org = OM.Organization.query.get(_id=self.org._id)
        assert len(self.org.getWorkfields()) == 1
        assert self.org.getWorkfields()[0]._id == wf._id
        assert wf.name in r
        assert wf.description in r
        
        #Add a second workfield
        wf2 = OM.WorkFields.query.get(name='Web applications')

        r = self.app.post('/organization/%s/add_work_field' % self.name,
            params = dict(
                workfield = str(wf2._id)),
            extra_environ=dict(username='test-user-1'))

        r = self.app.get('/organization/%s/' % self.name)
        
        self.org = OM.Organization.query.get(_id=self.org._id)
        assert len(self.org.getWorkfields()) == 2
        assert wf2.name in r
        assert wf2.description in r

        #Remove a workfield
        r = self.app.post('/organization/%s/remove_work_field' % self.name,
            params = {'workfieldid' : str(wf._id)},
            extra_environ=dict(username='test-user-1'))

        r = self.app.get('/organization/%s/' % self.name)
        assert len(self.org.getWorkfields()) == 1
        assert self.org.getWorkfields()[0]._id == wf2._id
        assert wf.name not in r
        assert wf.description not in r

class TestOrganizationMembership(TestOrganization):

    @td.with_user_project('test-user-1')
    def test_invalid_close_membership(self):
        m = OM.Membership.query.get(
            member_id=c.user._id, 
            organization_id=self.org._id)
        
        #Try to close the created membership
        r = self.app.post('/organization/%s/change_membership' % self.name,
            params=dict(
                status = 'closed',
                permission = 'admin',
                membershipid = str(m._id),
                requestfrom = 'user',
                role = self.role),
            extra_environ=dict(username='test-user-1'))

        #Since there aren't other admins, check that nothing changed
        m = OM.Membership.query.get(
            member_id=c.user._id, 
            organization_id=self.org._id)
        assert self.org.userPermissions(c.user) == 'admin'
        assert m.status == 'active'
        assert m.role == self.role

    @td.with_user_project('test-user-1')
    def test_invite_user(self):
        #Try to invite a new user
        user3 = User.by_username('test-admin')
        testrole = 'Software Engineer'

        r = self.app.post('/organization/%s/invite_user' % self.name,
            params=dict(
                username = user3.username,
                role = testrole),
            extra_environ=dict(username='test-user-1'))
        
        r = self.app.get('/organization/%s/edit_profile' % self.name,
            extra_environ=dict(username='test-user-1'))
        assert user3.display_name in r

        m = OM.Membership.query.get(
            member_id=user3._id, 
            organization_id=self.org._id)
        assert m.status == 'invitation'
        assert m.role == testrole

        #Accept invitation
        r = self.app.post('/organization/%s/change_membership' % self.name,
            params=dict(
                status = 'active',
                permission = 'member',
                membershipid = str(m._id),
                requestfrom = 'user',
                role = testrole),
            extra_environ=dict(username='test-admin'))

        m = OM.Membership.query.get(
            member_id=user3._id, 
            organization_id=self.org._id)
        assert m.status == 'active'
        assert m.role == testrole
        assert m.membertype == 'member'

    @td.with_user_project('test-user-1')
    def test_change_permissions(self):
        m = OM.Membership.query.get(
            member_id=self.user2._id, 
            organization_id=self.org._id)

        #Change permissions of the non-admin user
        r = self.app.post('/organization/%s/change_membership' % self.name,
            params=dict(
                status = 'active',
                permission = 'admin',
                membershipid = str(m._id),
                requestfrom = 'organization',
                role = 'Software Engineer'),
            extra_environ=dict(username='test-user-1'))

        m = OM.Membership.query.get(
            member_id=self.user2._id, 
            organization_id=self.org._id)
        assert m.status == 'active'
        assert m.role == 'Software Engineer'
        assert m.membertype == 'admin'

        #Close the involvement of test-user-1
        testuser1 = User.by_username('test-user-1')
        m = OM.Membership.query.get(
            member_id=testuser1._id, 
            organization_id=self.org._id)

        r = self.app.post('/organization/%s/change_membership' % self.name,
            params=dict(
                status = 'closed',
                permission = 'admin',
                membershipid = str(m._id),
                requestfrom = 'user',
                role = self.role),
            extra_environ=dict(username='test-user-1'))

        m = OM.Membership.query.get(
            member_id=c.user._id, 
            organization_id=self.org._id)
        assert self.org.userPermissions(c.user) == 'admin'
        assert m.status == 'closed'
        assert m.role == self.role


    @td.with_user_project('test-admin')
    def test_send_request(self):
        #Send an admission new user
        user3 = User.by_username('test-admin')
        testrole = 'Software Engineer'

        r = self.app.post('/organization/%s/admission_request' % self.name,
            params=dict(
                role = testrole),
            extra_environ=dict(username='test-admin'))
        
        r = self.app.get('/organization/%s/edit_profile' % self.name,
            extra_environ=dict(username='test-user-1'))
        assert user3.display_name in r

        m = OM.Membership.query.get(
            member_id=user3._id, 
            organization_id=self.org._id)
        assert m.status == 'request'
        assert m.role == testrole

        #Check that the user is not allowed to accept his own request
        r = self.app.post('/organization/%s/change_membership' % self.name,
            params=dict(
                status = 'active',
                permission = 'member',
                membershipid = str(m._id),
                requestfrom = 'user',
                role = testrole),
            extra_environ=dict(username='test-admin'))

        m = OM.Membership.query.get(
            member_id=user3._id, 
            organization_id=self.org._id)
        assert m.status == 'request'

        #Accept request
        r = self.app.post('/organization/%s/change_membership' % self.name,
            params=dict(
                status = 'active',
                permission = 'member',
                membershipid = str(m._id),
                requestfrom = 'user',
                role = testrole),
            extra_environ=dict(username='test-user-1'))

        m = OM.Membership.query.get(
            member_id=user3._id, 
            organization_id=self.org._id)
        assert m.status == 'active'
        assert m.role == testrole
        assert m.membertype == 'member'

#check progetti

class TestOrganizationProjects(TestOrganization):

    @td.with_user_project('test-admin')
    def test_request_collaboration(self):
        def send_request(self):
            #Try to send a request to participate to a project
            #The user sending the request is the admin of the org's profile
            r = self.app.post('/organizationstool/send_request',
                params=dict(
                    organization = str(self.org._id),
                    coll_type = 'cooperation'),
                extra_environ=dict(username='test-user-1'))
            return OM.ProjectInvolvement.query.get(organization_id=self.org._id)
       
        p = send_request(self)
        assert p.status == 'request'
        assert p.collaborationtype == 'cooperation'

        #As the admin of the project, reject pending request
        r = self.app.post('/organizationstool/update_collaboration_status',
            params=dict(
                collaborationid = str(p._id),
                collaborationtype = 'cooperation',
                status = 'remove'),
            extra_environ=dict(username='test-admin'))

        p = OM.ProjectInvolvement.query.get(organization_id=self.org._id)        
        assert p is None

        p = send_request(self)

        #As the admin of the project, accept pending request
        r = self.app.post('/organizationstool/update_collaboration_status',
            params=dict(
                collaborationid = str(p._id),
                collaborationtype = 'cooperation',
                status = 'active'),
            extra_environ=dict(username='test-admin'))
        
        assert p.status == 'active'
        assert p.collaborationtype == 'cooperation'

        #As the admin of the project, close the collaboration
        r = self.app.post('/organizationstool/update_collaboration_status',
            params=dict(
                collaborationid = str(p._id),
                collaborationtype = 'cooperation',
                status = 'closed'),
            extra_environ=dict(username='test-admin'))
        
        p = OM.ProjectInvolvement.query.get(organization_id=self.org._id)        
        assert p.status == 'closed'
        assert p.collaborationtype == 'cooperation'

    @td.with_user_project('test-admin')
    def test_invite_organization(self):
        def send_invitation(self):
            #Try to send an invitation to participate to a project
            #The user sending the request is the admin of the project
            r = self.app.post('/organizationstool/invite',
                params=dict(
                    organizationid = str(self.org._id),
                    collaborationtype = 'cooperation'),
                extra_environ=dict(username='test-admin'))
            return OM.ProjectInvolvement.query.get(organization_id=self.org._id)
       
        p = send_invitation(self)
        assert p.status == 'invitation'
        assert p.collaborationtype == 'cooperation'

        #As the admin of the organization, reject pending invitation
        r = self.app.post('/organization/%s/update_collaboration_status' % self.name,
            params=dict(
                collaborationid = str(p._id),
                collaborationtype = 'cooperation',
                status = 'remove'),
            extra_environ=dict(username='test-user-1'))

        p = OM.ProjectInvolvement.query.get(organization_id=self.org._id)        
        assert p is None

        p = send_invitation(self)

        #As the admin of the organization, accept pending invitation
        r = self.app.post('/organization/%s/update_collaboration_status' % self.name,
            params=dict(
                collaborationid = str(p._id),
                collaborationtype = 'cooperation',
                status = 'active'),
            extra_environ=dict(username='test-user-1'))
        
        assert p.status == 'active'
        assert p.collaborationtype == 'cooperation'

        #As the admin of the organization, close the collaboration
        r = self.app.post('/organization/%s/update_collaboration_status' % self.name,
            params=dict(
                collaborationid = str(p._id),
                collaborationtype = 'cooperation',
                status = 'closed'),
            extra_environ=dict(username='test-user-1'))
        
        p = OM.ProjectInvolvement.query.get(organization_id=self.org._id)        
        assert p.status == 'closed'
        assert p.collaborationtype == 'cooperation'
