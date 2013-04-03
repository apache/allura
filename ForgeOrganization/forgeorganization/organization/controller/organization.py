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
        o = Organization.register(shortname, fullname, orgtype, c.user)
        if o is None: 
            flash(
                'The short name "%s" has been taken by another organization.' \
                % shortname, 'error')
            redirect('/organization/register')
        m = Membership.insert(role, 'active', o._id, c.user._id)
        flash('Organization "%s" correctly created!' % fullname)
        redirect('%sadmin/organizationprofile' % o.url())

    @expose()
    @require_post()
    @validate(V.NullValidator(), error_handler=index)
    def change_membership(self, **kw):        
        membershipid = kw['membershipid']
        memb = Membership.getById(membershipid)
        status = kw['status']

        return_url = '/organization'

        if c.user != memb.member:
            flash(
                "You don't have the permission to perform this action.", 
                "error")
            redirect(return_url)

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
        if memb.status=='request' and status=='active':
            allowed=False

        if allowed:
            memb.setStatus(status)
            memb.role = kw.get('role')
            flash('The membership has been successfully updated.')
        else:
            flash("You are not allowed to perform this action.")
        redirect(return_url)
