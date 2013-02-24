from tg import expose, validate, redirect, flash
from tg.decorators import with_trailing_slash
from pylons import c
from allura.lib import validators as V
from allura.lib.decorators import require_post
from allura import model as M
from allura.lib.security import require_authenticated
from allura.controllers import BaseController
import forgeorganization.tool.widgets.forms as forms 
from forgeorganization.organization.model import Organization
from forgeorganization.organization.model import ProjectInvolvement
import re
from datetime import datetime

class Forms(object):
    search_form=forms.SearchOrganizationForm(action='search')
    invite_form=forms.InviteOrganizationForm(action='invite')
    collaboration_request_form=forms.SendCollaborationRequestForm(
        action='send_request')
    def new_change_status_form(self):
        return forms.ChangeCollaborationStatusForm(
            action='update_collaboration_status')

F = Forms()

class OrganizationToolController(BaseController):

    @expose('jinja:forgeorganization:tool/templates/index.html')
    @with_trailing_slash
    def index(self, **kw):
        is_admin=c.user.username in c.project.admins()
        cooperations=[el for el in c.project.organizations
                      if el.collaborationtype=='cooperation']
        participations=[el for el in c.project.organizations
                        if el.collaborationtype=='participation']
        user_organizations=[o.organization for o in c.user.memberships
                            if o.membertype == 'admin']
        return dict(
            user_organizations=user_organizations,
            cooperations=cooperations, 
            participations=participations,
            is_admin=is_admin,
            forms = F)

    @expose('jinja:forgeorganization:tool/templates/search_results.html')
    @require_post()
    @with_trailing_slash
    @validate(F.search_form, error_handler=index)
    def search(self, organization, **kw):
        regx = re.compile(organization, re.IGNORECASE)
        orgs = Organization.query.find(dict(fullname=regx))
        return dict(
            orglist = orgs, 
            forms = F,
            search_string = organization)

    @expose()
    @require_post()
    @validate(V.NullValidator(), error_handler=index)
    def invite(self, organizationid, collaborationtype, **kw):
        require_authenticated()
        is_admin=c.user.username in c.project.admins()
        if not is_admin:
            flash("You are not allowed to perform this action", "error")
            redirect(".")
            return
        org = Organization.getById(organizationid)
        if not org:
            flash("Invalid organization.", "error")
            redirect(".")
            return
        result = ProjectInvolvement.insert(
            status='invitation', 
            collaborationtype=collaborationtype, 
            organization_id=organizationid, 
            project_id=c.project._id)
        if not result:
            flash("This organization is already involved in this project.",
                  "error")
        else:
            flash("Invitation correctly sent.")
        redirect(".")

    @expose()
    @require_post()
    @validate(V.NullValidator(), error_handler=index)
    def update_collaboration_status(self, collaborationid, collaborationtype, status, **kw):
        require_authenticated()
        is_admin=c.user.username in c.project.admins()
        if not is_admin:
            flash("You are not allowed to perform this action", "error")
            redirect(".")
            return

        allowed = True
        coll = ProjectInvolvement.getById(collaborationid)
        if not coll:
            allowed = False
        if coll.status != status:
            if coll.status=='invitation' and status!='remove':
                allowed=False
            elif coll.status=='closed':
                allowed=False
            elif coll.status=='active' and status!='closed':
                allowed=False
            elif coll.status=='request' and status not in ['active','remove']:
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
        redirect('.')

    @expose()
    @require_post()
    @validate(V.NullValidator(), error_handler=index)
    def send_request(self, organization, coll_type, **kw):
        organization = Organization.getById(organization)     

        if not organization or organization.userPermissions(c.user)!='admin':
            flash("You are not allowed to perform this action.", "error")
            redirect(".")
            return
        
        for org in c.project.organizations:
            if org.organization == organization and org.status!='closed':
                flash(
                    "This organization is already included in this project.",
                    "error")
                redirect(".")
                return
        ProjectInvolvement.insert('request', coll_type, organization._id, 
            c.project._id)
        flash("Your collaboration request was successfully sent.")
        redirect(".")
        return
