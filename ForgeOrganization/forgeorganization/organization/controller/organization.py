from tg import expose, flash, redirect, validate
from tg.decorators import with_trailing_slash
import pylons
c = pylons.c = pylons.tmpl_context
g = pylons.g = pylons.app_globals
import re

from allura.lib import validators as V
from allura.lib.security import require_authenticated
from allura.lib.decorators import require_post
import allura.model as M
from allura.controllers import BaseController
import forgeorganization.organization.widgets.forms as forms
from forgeorganization.organization.model import Organization, Membership
from forgeorganization.organization.model import WorkFields, ProjectInvolvement
from datetime import datetime
from pkg_resources import get_entry_info

class Forms(object):
    registration_form = forms.RegistrationForm(action='/organization/save_new')
    search_form = forms.SearchForm(action='/organization/search')
    update_profile = forms.UpdateProfile()
    add_work_field = forms.AddWorkField()
    remove_work_field = forms.RemoveWorkField()
    invite_user_form = forms.InviteUser()
    admission_request_form = forms.RequestAdmissionForm()
    request_collaboration_form = forms.RequestCollaborationForm()

    def new_change_collaboration_status(self):
        return forms.ChangeCollaborationStatusForm()

    def new_change_membership_from_user_form(self):
        return forms.ChangeMembershipFromUser()
    
    def new_change_membership_from_organization(self):
        return forms.ChangeMembershipFromOrganization()

F = Forms()

class OrganizationController(object):
    @expose()
    def _lookup(self, shortname, *remainder):
        org = Organization.query.get(shortname=shortname)
        if not org:
            return OrganizationController(), remainder
        else:
            return OrganizationProfileController(organization=org), remainder

    @expose('jinja:forgeorganization:organization/templates/user_memberships.html')
    def index(self, **kw):
        require_authenticated()

        return dict(
            memberships=[m for m in c.user.memberships if m.status!='closed'],
            forms=F)

    @expose('jinja:forgeorganization:organization/templates/search_results.html')
    @require_post()
    @validate(F.search_form, error_handler=index)
    def search(self, orgname, **kw):
        regx = re.compile(orgname, re.IGNORECASE)
        orgs = Organization.query.find(dict(fullname=regx))
        return dict(
            orglist = orgs, 
            forms = F, 
            search_string = orgname)

    @expose('jinja:forgeorganization:organization/templates/register.html')
    def register(self, **kw):
        require_authenticated()
        return dict(forms=F)

    @expose()
    @require_post()
    @validate(F.registration_form, error_handler=register)
    def save_new(self, fullname, shortname, orgtype, role, **kw):
        o = Organization.register(shortname, fullname, orgtype)
        if o is None: 
            flash(
                'The short name "%s" has been taken by another organization.' \
                % shortname, 'error')
            redirect('/organization/register')
        m = Membership.insert('admin', role, 'active', o._id, c.user._id)
        flash('Organization "%s" correctly created!' % fullname)
        redirect('/organization/%s/edit_profile' % shortname)

class OrganizationProfileController(BaseController):
    def __init__(self, organization):
        self.organization = organization
        super(OrganizationProfileController, self).__init__()

    @with_trailing_slash
    @expose('jinja:forgeorganization:organization/templates/organization_profile.html')
    def index(self, **kw):        
        activecoll=[coll for coll in self.organization.project_involvements
                    if coll.status=='active']
        closedcoll=[p for p in self.organization.project_involvements 
                    if p.status=='closed']

        role = self.organization.userPermissions(c.user)
        mlist=[m for m in self.organization.memberships if m.status=='active']
        plist=[m for m in self.organization.memberships if m.status=='closed']

        is_admin = (role == 'admin')
        
        return dict(
            workfields = WorkFields.query.find(),
            members = mlist,
            past_members=plist,
            active_collaborations=activecoll,
            closed_collaborations=closedcoll,
            organization = self.organization,
            is_member = (role is not None),
            is_admin = (role =='admin'),
            forms = F)
        
    @expose('jinja:forgeorganization:organization/templates/edit_profile.html')
    def edit_profile(self, **kw):
        require_authenticated()
        
        mlist=[m for m in self.organization.memberships if m.status!='closed']
        clist=[el for el in self.organization.project_involvements 
               if el.status!='closed']

        return dict(
            permissions = self.organization.userPermissions(c.user),
            organization = self.organization,
            members = mlist,
            collaborations= clist,
            forms = F)

    @expose()
    @require_post()
    @validate(F.update_profile, error_handler=edit_profile)
    def change_data(self, **kw):
        require_authenticated()
        if self.organization.userPermissions(c.user) != 'admin':
            flash(
                "You don't have the permission to perform this action.", 
                "error")
            redirect(self.organization.url())
        self.organization.organization_type = kw['organization_type']
        self.organization.fullname = kw['fullname']
        self.organization.description = kw['description']
        self.organization.headquarters = kw['headquarters']
        self.organization.dimension = kw['dimension']
        self.organization.website = kw['website']

        flash('The organization profile has been successfully updated.')
        redirect(self.organization.url()+'edit_profile')

    @expose()
    @require_post()
    @validate(F.remove_work_field, error_handler=edit_profile)
    def remove_work_field(self, **kw):
        require_authenticated()
        if self.organization.userPermissions(c.user) != 'admin':
            flash(
                "You don't have the permission to perform this action.", 
                "error")
            redirect(self.organization.url())
        self.organization.removeWorkField(kw['workfield'])
        flash('The organization profile has been successfully updated.')
        redirect(self.organization.url()+'edit_profile')

    @expose()
    @require_post()
    @validate(V.NullValidator(), error_handler=edit_profile)
    def add_work_field(self, workfield, **kw):
        require_authenticated()
        workfield = WorkFields.getById(workfield)

        if workfield is None:
            flash("Invalid workfield. Select a valid value.", "error")
            redirect(self.organization.url()+'edit_profile')

        if self.organization.userPermissions(c.user)!='admin':
            flash(
                "You don't have the permission to perform this action.", 
                "error")
            redirect(self.organization.url())
        self.organization.addWorkField(workfield)
        flash('The organization profile has been successfully updated.')
        redirect(self.organization.url()+'edit_profile')

    @expose()
    @require_post()
    @validate(F.invite_user_form, error_handler=edit_profile)
    def invite_user(self, **kw):
        require_authenticated()
        username = kw['username']
        if self.organization.userPermissions(c.user) != 'admin':
            flash(
                "You don't have the permission to perform this action.", 
                "error")
            redirect(self.organization.url())
        user = M.User.query.get(username=kw['username'])
        if not user:
            flash(
                '''The username "%s" doesn't belong to any user on the forge'''\
                % username, "error")
            redirect(self.organization.url() + 'edit_profile')

        invitation = Membership.insert('member', kw['role'], 'invitation', 
            self.organization._id, user._id)
        if invitation:
            flash(
                'The user '+ username +' has been successfully invited to '+ \
                'become a member of the organization.')
        else:
            flash(
                username+' is already a member of the organization.', 'error')

        redirect(self.organization.url()+'edit_profile')

    @expose()
    @require_post()
    @validate(V.NullValidator(), error_handler=index)
    def change_membership(self, **kw):
        require_authenticated()
        
        membershipid = kw['membershipid']
        memb = Membership.getById(membershipid)
        status = kw['status']
        new_permission = kw['permission']
        
        if memb:
            user_permission = memb.organization.userPermissions(c.user)
        if memb is None or (memb.member!=c.user and user_permission!='admin'):
            flash(
                "You don't have the permission to perform this action.", 
                "error")
            redirect('/organization')
            return

        if kw.get('requestfrom') == 'user':
           return_url = '/organization'
        else:
           return_url = memb.organization.url() + 'edit_profile'

        if status == 'remove':
            old_status = memb.status
            if memb.status in ['invitation', 'request']:
                Membership.delete(memb)
                flash('The pending %s has been removed.' % old_status)
                redirect(return_url)
                return
            else:
                flash(
                    "You don't have the permission to perform this action.", 
                    "error")
                redirect(return_url)
                return

        if status == 'closed' and memb.membertype == 'admin':
            if len(memb.organization.getAdministrators())==1:
                flash(
                    'This user is the only administrator of the organization, '+\
                    'therefore, before closing this enrollment, another '+\
                    'administrator has to be set.', 'error')
                redirect(return_url)
                return                

        if status == 'closed':
            new_permission = memb.membertype

        allowed=True
        if memb.status=='closed' and status!='closed':
            allowed=False
        if memb.status=='request' and status=='active' and user_permission!='admin':
            allowed=False
        if memb.status=='invitation' and status=='active' and memb.member!=c.user:
            allowed=False
        if new_permission != memb.membertype:
            if user_permission!='admin' and memb.member != c.user:
                allowed = False
            admins = memb.organization.getAdministrators()
            if new_permission == 'member' and len(admins)==1:
                flash(
                    'This user is the only administrator of the organization, '+\
                    'therefore, before changing his permission level, another '+\
                    'administrator has to be set.', 'error')
                redirect(return_url)
                return

        if allowed:
            memb.setStatus(status)
            memb.membertype = new_permission
            memb.role = kw.get('role')
            if new_permission=='member' and memb.member == c.user:
                return_url = '/organization'
            flash('The membership has been successfully updated.')
        else:
            flash("You are not allowed to perform this action.")
        redirect(return_url)

    @expose()
    @require_post()
    @validate(F.admission_request_form, error_handler=index)
    def admission_request(self, role, **kw):
        require_authenticated()
        m=Membership.insert(
            'member', role, 'request', self.organization._id, c.user._id)
        flash('Request sent')
        redirect('/organization/')

    @expose()
    @require_post()
    @validate(F.request_collaboration_form, error_handler=edit_profile)
    def send_collaboration_request(self, project_url_name, collaboration_type, **kw):
        require_authenticated()
        user_permission = self.organization.userPermissions(c.user)
        if user_permission != 'admin':
            flash(
                "You don't have the permission to perform this action.", 
                "error")
            redirect('/organization')
            return
        project=M.Project.query.get(shortname=project_url_name)
        if not project:
            flash(
                "Invalid URL name. Please, insert the URL name of an existing "+\
                "project.", "error")
        else:
            ProjectInvolvement.insert('request', collaboration_type, 
                self.organization._id, project._id)
            flash("Collaboration request successfully sent.")
        redirect('%sedit_profile' % self.organization.url())
            
    @expose()
    @require_post()
    @validate(V.NullValidator(), error_handler=edit_profile)
    def update_collaboration_status(self, collaborationid, collaborationtype, status, **kw):
        require_authenticated()

        coll = ProjectInvolvement.getById(collaborationid)
        user_permission = coll.organization.userPermissions(c.user)
        if user_permission != 'admin':
            flash(
                "You don't have the permission to perform this action.", 
                "error")
            redirect('/organization')
            return

        allowed = True
        if coll.status != status:
            if coll.status=='invitation' and status not in ['active','remove']:
                allowed=False
            elif coll.status=='closed':
                allowed=False
            elif coll.status=='active' and status!='closed':
                allowed=False
            elif coll.status=='request' and status !='remove':
                allowed=False

        if allowed:
            if status=='closed':
                collaborationtype=coll.collaborationtype

            if status=='remove':
                ProjectInvolvement.delete(coll._id)
            else:
                coll.collaborationtype=collaborationtype
                coll.setStatus(status)
            flash('The information about this collaboration has been updated')
        else:
            flash("You are not allowed to perform this action", "error")
        redirect('%sedit_profile' % coll.organization.url())
