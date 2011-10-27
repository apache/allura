""" ForgeDiscussion utilities. """

from bson import ObjectId
from tg import flash
from allura.lib import helpers as h
from allura.model import ProjectRole, ACE, ALL_PERMISSIONS, DENY_ALL
from forgediscussion import model as DM

def save_forum_icon(forum, icon):
    if forum.icon: forum.icon.delete()
    DM.ForumFile.save_image(
        icon.filename, icon.file, content_type=icon.type,
        square=True, thumbnail_size=(48, 48),
        thumbnail_meta=dict(forum_id=forum._id))

def create_forum(app, new_forum):
    if 'parent' in new_forum and new_forum['parent']:
        parent_id = ObjectId(str(new_forum['parent']))
        shortname = (DM.Forum.query.get(_id=parent_id).shortname + '/'
                        + new_forum['shortname'])
    else:
        parent_id=None
        shortname = new_forum['shortname']
    description = ''
    if 'description' in new_forum:
        description=new_forum['description']
    if 'anon_posts' in new_forum:
        anon_posts=new_forum['anon_posts']
    else:
        anon_posts = False
    if 'members_only' in new_forum and new_forum['members_only']:
        if anon_posts:
            flash('You cannot have anonymous posts in a members only forum.', 'warning')
            anon_posts = False
        members_only=new_forum['members_only']
    else:
        members_only = False
    f = DM.Forum(app_config_id=app.config._id,
                    parent_id=parent_id,
                    name=h.really_unicode(new_forum['name']),
                    shortname=h.really_unicode(shortname),
                    description=h.really_unicode(description),
                    members_only=members_only)
    if members_only:
        role_developer = ProjectRole.by_name('Developer')._id
        f.acl = [
            ACE.allow(role_developer, ALL_PERMISSIONS),
            DENY_ALL]
    else:
        f.acl = []
    role_anon = ProjectRole.anonymous()._id
    if members_only:
        role_developer = ProjectRole.by_name('Developer')._id
        f.acl = [
            ACE.allow(role_developer, ALL_PERMISSIONS),
            DENY_ALL]
    elif anon_posts:
        f.acl = [ACE.allow(role_anon, 'post')]
    else:
        f.acl = []
    if 'icon' in new_forum and new_forum['icon'] is not None and new_forum['icon'] != '':
        save_forum_icon(f, new_forum['icon'])
    return f
