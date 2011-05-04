from datetime import datetime

from pylons import g

from ming import schema as S
from ming.orm import MappedClass, FieldProperty
from allura import model as M

class ChatChannel(MappedClass):

    class __mongometa__:
        name = 'globals'
        session = M.main_orm_session
        unique_indexes = [ 'channel' ]

    _id = FieldProperty(S.ObjectId)
    project_id = FieldProperty(S.ObjectId)
    app_config_id = FieldProperty(S.ObjectId)
    channel = FieldProperty(str)

class ChatMessage(M.Artifact):
    class __mongometa__:
        name='chat_message'
        indexes = [ 'timestamp' ]
    type_s='Chat Message'

    timestamp = FieldProperty(datetime, if_missing=datetime.utcnow)
    sender = FieldProperty(str, if_missing='')
    channel = FieldProperty(str, if_missing='')
    text = FieldProperty(str, if_missing='')

    def index_id(self):
        id = 'Chat-%s:%s:%s.%s' % (
            self.channel,
            self.sender,
            self.timestamp.isoformat(),
            self._id)
        return id.replace('.', '/')

    def index(self):
        result = super(ChatMessage, self).index()
        result.update(
            snippet_s='%s > %s' % (self.sender, self.text),
            sender_t=self.sender,
            text=self.text)
        return result

    def url(self):
        return (self.app_config.url()
                + self.timestamp.strftime('%Y/%m/%d/#')
                + str(self._id))

    def shorthand_id(self):
        return str(self._id) # pragma no cover

    @property
    def html_text(self):
        text = '**%s** *%s* &mdash; %s' % (
            self.timestamp_hour,
            self.sender_short,
            self.text)
        return g.markdown.convert(text)

    @property
    def sender_short(self):
        return self.sender.split('!')[0]

    @property
    def timestamp_hour(self):
        return self.timestamp.strftime('%H:%M:%S')

MappedClass.compile_all()
