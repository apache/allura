import logging
from pprint import pformat

import pkg_resources
from pylons import tmpl_context as c, app_globals as g
from pylons import request
from formencode import validators
from tg import expose, redirect, validate, response, flash
from webob import exc

from allura import version
from allura.app import Application, SitemapEntry
from allura.lib import helpers as h
from allura.lib.helpers import DateTimeConverter
from allura.lib.security import require_access
import allura.model as M
from allura.model import User, Feed, ACE
from allura.controllers import BaseController
from allura.lib.decorators import require_post

from forgeorganization.organization.model import Organization, WorkFields, Membership, ProjectInvolvement

import forgeorganization.organization.widgets.forms as forms
from allura.lib import validators as V
from allura.lib.security import require_authenticated
from allura.lib.decorators import require_post

log = logging.getLogger(__name__)

class Forms(object):
    update_profile = forms.UpdateProfile()
    add_work_field = forms.AddWorkField()
    remove_work_field = forms.RemoveWorkField()
    invite_user_form = forms.InviteUser()
    admission_request_form = forms.RequestAdmissionForm()
    request_collaboration_form = forms.RequestCollaborationForm()
    def new_change_collaboration_status(self):
        return forms.ChangeCollaborationStatusForm()
    def new_change_membership_from_organization(self):
        return forms.ChangeMembershipFromOrganization()

F = Forms()

class OrganizationProfileApp(Application):
    __version__ = version.__version__
    installable = False
    icons={
        24:'images/home_24.png',
        32:'images/home_32.png',
        48:'images/home_48.png'
    }

    def __init__(self, user, config):
        Application.__init__(self, user, config)
        self.root = OrganizationProfileController()
        self.admin = OrganizationProfileAdminController()

    def admin_menu(self):
        links = [SitemapEntry(
            'Edit',
            '%sadmin/organizationprofile' % c.project.organization_project_of.url())]
        return links

    def install(self, project):
        pr = c.user.project_role()
        if pr:
            self.config.acl = [
                ACE.allow(pr._id, perm)
                for perm in self.permissions ]

    def uninstall(self, project):
        pass

    @property
    @h.exceptionless([], log)
    def sitemap(self):
        return []

class OrganizationProfileController(BaseController):

    @expose('jinja:forgeorganization:organization_profile/templates/organization_index.html')
    def index(self, **kw):
        organization = c.project.organization_project_of
        if not organization:
            raise exc.HTTPNotFound()
        activecoll=[coll for coll in organization.project_involvements
                    if coll.status=='active']
        closedcoll=[p for p in organization.project_involvements 
                    if p.status=='closed']
        mlist=[m for m in organization.memberships if m.status=='active']
        plist=[m for m in organization.memberships if m.status=='closed']
        return dict(
            forms = F,
            ask_admission = (c.user not in [m.member for m in mlist]) and c.user != M.User.anonymous(),
            workfields = WorkFields.query.find(),
            organization=organization,
            members = mlist,
            past_members=plist,
            active_collaborations=activecoll,
            closed_collaborations=closedcoll)

    @expose()
    @require_post()
    @validate(F.admission_request_form, error_handler=index)
    def admission_request(self, role, **kw):
        require_access(c.project, 'read')
        m=Membership.insert(
            role, 'request', c.project.organization_project_of._id, c.user._id)
        flash('Request sent')
        redirect(c.project.organization_project_of.url()+'organizationprofile')

class OrganizationProfileAdminController(BaseController):
    @expose('jinja:forgeorganization:organization_profile/templates/edit_profile.html')
    def index(self, **kw):
        require_access(c.project, 'admin')
        
        organization = c.project.organization_project_of
        mlist=[m for m in organization.memberships if m.status!='closed']
        clist=[el for el in organization.project_involvements 
               if el.status!='closed']

        return dict(
            organization = organization,
            members = mlist,
            collaborations= clist,
            forms = F)

    @expose()
    @require_post()
    @validate(F.remove_work_field, error_handler=index)
    def remove_work_field(self, **kw):
        require_access(c.project, 'admin')
        c.project.organization_project_of.removeWorkField(kw['workfield'])
        flash('The organization profile has been successfully updated.')
        redirect(c.project.organization_project_of.url()+'admin/organizationprofile')

    @expose()
    @require_post()
    @validate(V.NullValidator(), error_handler=index)
    def add_work_field(self, workfield, **kw):
        require_access(c.project, 'admin')
        workfield = WorkFields.getById(workfield)

        if workfield is None:
            flash("Invalid workfield. Select a valid value.", "error")
            redirect(c.project.organization_project_of.url()+'admin/organizationprofile')
        c.project.organization_project_of.addWorkField(workfield)
        flash('The organization profile has been successfully updated.')
        redirect(c.project.organization_project_of.url()+'admin/organizationprofile')

    @expose()
    @require_post()
    @validate(F.invite_user_form, error_handler=index)
    def invite_user(self, **kw):
        require_access(c.project, 'admin')
        username = kw['username']
        user = M.User.query.get(username=kw['username'])
        if not user:
            flash(
                '''The username "%s" doesn't belong to any user on the forge'''\
                % username, "error")
            redirect(c.project.organization_project_of.url() + 'admin/organizationprofile')

        invitation = Membership.insert(kw['role'], 'invitation', 
            c.project.organization_project_of._id, user._id)
        if invitation:
            flash(
                'The user '+ username +' has been successfully invited to '+ \
                'become a member of the organization.')
        else:
            flash(
                username+' is already a member of the organization.', 'error')

        redirect(c.project.organization_project_of.url()+'admin/organizationprofile')

    @expose()
    @require_post()
    @validate(V.NullValidator(), error_handler=index)
    def change_membership(self, **kw):        
        membershipid = kw['membershipid']
        memb = Membership.getById(membershipid)
        status = kw['status']

        return_url = memb.organization.url() + 'admin/organizationprofile'

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

        allowed=True
        if memb.status=='closed' and status!='closed':
            allowed=False
        if memb.status=='invitation' and status=='active':
            allowed=False

        if allowed:
            memb.setStatus(status)
            memb.role = kw.get('role')
            flash('The membership has been successfully updated.')
        else:
            flash("You are not allowed to perform this action.")
        redirect(return_url)

    @expose()
    @require_post()
    @validate(F.request_collaboration_form, error_handler=index)
    def send_collaboration_request(self, project_url_name, collaboration_type, **kw):
        require_access(c.project, 'admin')
        project=M.Project.query.get(shortname=project_url_name)
        if not project:
            flash(
                "Invalid URL name. Please, insert the URL name of an existing "+\
                "project.", "error")
        else:
            ProjectInvolvement.insert('request', collaboration_type, 
                c.project.organization_project_of._id, project._id)
            flash("Collaboration request successfully sent.")
        redirect('%sadmin/organizationprofile' % c.project.organization_project_of.url())
            
    @expose()
    @require_post()
    @validate(V.NullValidator(), error_handler=index)
    def update_collaboration_status(self, collaborationid, collaborationtype, status, **kw):
        require_access(c.project, 'admin')

        coll = ProjectInvolvement.getById(collaborationid)

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
        redirect('%sadmin/organizationprofile' % coll.organization.url())

    @expose()
    @require_post()
    @validate(F.update_profile, error_handler=index)
    def change_data(self, **kw):
        require_access(c.project, 'admin')

        c.project.organization_project_of.organization_type = kw['organization_type']
        c.project.organization_project_of.fullname = kw['fullname']
        c.project.organization_project_of.description = kw['description']
        c.project.organization_project_of.headquarters = kw['headquarters']
        c.project.organization_project_of.dimension = kw['dimension']
        c.project.organization_project_of.website = kw['website']

        flash('The organization profile has been successfully updated.')
        redirect(c.project.organization_project_of.url() + 'admin/organizationprofile')
