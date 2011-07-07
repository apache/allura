""" ForgeDiscussion utilities. """

from bson import ObjectId
from allura.lib import helpers as h
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
    f = DM.Forum(app_config_id=app.config._id,
                    parent_id=parent_id,
                    name=h.really_unicode(new_forum['name']).encode('utf-8'),
                    shortname=h.really_unicode(shortname).encode('utf-8'),
                    description=h.really_unicode(description).encode('utf-8'))
    if 'icon' in new_forum and new_forum['icon'] is not None and new_forum['icon'] != '':
        save_forum_icon(f, new_forum['icon'])
    return f
