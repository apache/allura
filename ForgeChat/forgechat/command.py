#       Licensed to the Apache Software Foundation (ASF) under one
#       or more contributor license agreements.  See the NOTICE file
#       distributed with this work for additional information
#       regarding copyright ownership.  The ASF licenses this file
#       to you under the Apache License, Version 2.0 (the
#       "License"); you may not use this file except in compliance
#       with the License.  You may obtain a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#       Unless required by applicable law or agreed to in writing,
#       software distributed under the License is distributed on an
#       "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
#       KIND, either express or implied.  See the License for the
#       specific language governing permissions and limitations
#       under the License.


import six
import time
import logging
import socket
import asyncore
import asynchat
import random
from six.moves.urllib.parse import urljoin
from datetime import datetime, timedelta

import tg
from paste.script import command
from paste.deploy.converters import asint

from ming.orm import ThreadLocalORMSession

import allura
from allura.command import base
from allura.lib import helpers as h
from allura.lib import search, security
from allura import model as M

from forgechat import model as CM


class IRCBotCommand(allura.command.Command):
    min_args = 1
    max_args = 1
    usage = '<ini file>'
    summary = 'For the ForgeChat tool.  Connect to all configured IRC servers and relay messages'
    parser = command.Command.standard_parser(verbose=True)
    parser.add_option('-c', '--context', dest='context',
                      help=('The context of the message (path to the project'
                            ' and/or tool'))

    def command(self):
        self.basic_setup()
        base.log.info('IRCBot starting up...')
        while True:
            try:
                IRCBot(
                    tg.config.get('forgechat.host', 'irc.freenode.net'),
                    asint(tg.config.get('forgechat.port', '6667')))
                asyncore.loop()
            except Exception:
                base.log.exception(
                    'Error in ircbot asyncore.loop(), restart in 5s')
                time.sleep(5)


class IRCBot(asynchat.async_chat):
    TIME_BETWEEN_CONFIGS = timedelta(minutes=1)

    def __init__(self, host, port, nick=None):
        if nick is None:
            nick = tg.config.get('ircbot.nick', 'allurabot')
        self.logger = logging.getLogger(__name__)
        self.host = host
        self.port = port
        self.nick = nick
        sock = socket.socket()
        sock.connect((host, port))
        asynchat.async_chat.__init__(self, sock)
        self.set_terminator(b'\r\n')
        self.data = []
        self.channels = {}
        self.set_nick('000')
        self.say('USER {nick} {host} {host} :{nick} 0.0'.format(
            nick=self.nick,
            host=self.host))
        self.configure()

    def set_nick(self, suffix=None):
        if suffix is None:
            suffix = '%.3d' % random.randint(0, 999)
        nick = f'{self.nick}-{suffix}'
        self.say('NICK ' + nick)

    def collect_incoming_data(self, data):
        self.data.append(six.ensure_text(data))

    def found_terminator(self):
        request = ''.join(self.data)
        self.logger.debug('RECV %s', request)
        self.data = []
        if request.startswith(':'):
            sender, cmd, rest = request[1:].split(' ', 2)
            sender = sender.split('!', 1)
        else:
            sender = ('', '')
            cmd, rest = request.split(' ', 1)
        self.handle_command(sender, cmd, rest)

    def configure(self):
        new_channels = {
            ch.channel: ch for ch in CM.ChatChannel.query.find()}
        for channel in new_channels:
            if channel not in self.channels and channel:
                self.say('JOIN %s' % channel)
        for channel in self.channels:
            if channel not in new_channels and channel:
                self.say('LEAVE %s' % channel)
        self.channels = new_channels
        self.last_configured = datetime.utcnow()

    def check_configure(self):
        if (datetime.utcnow() - self.last_configured
                > self.TIME_BETWEEN_CONFIGS):
            self.configure()

    def say(self, s):
        s = s.encode('utf-8')
        self.logger.debug('SAYING %s', s)
        self.push(s + b'\r\n')

    def notice(self, out, message):
        self.say(f'NOTICE {out} :{message}')
        CM.ChatMessage(
            sender=self.nick,
            channel=out,
            text=message)
        ThreadLocalORMSession.flush_all()

    def handle_command(self, sender, cmd, rest):
        if cmd == 'NOTICE':
            pass
        elif cmd == '433':
            self.set_nick()
            self.channels = {}
            self.configure()
        elif cmd == 'PING':
            self.say('PONG ' + rest)
        elif cmd in ('NOTICE', 'PRIVMSG'):
            rcpt, msg = rest.split(' ', 1)
            if not self.set_context(rcpt):
                return
            if msg.startswith(':'):
                msg = msg[1:]
            self.log_channel(sender, cmd, rcpt, msg)
            if cmd == 'NOTICE':
                return
            for lnk in search.find_shortlinks(msg):
                self.handle_shortlink(lnk, sender, rcpt)
        ThreadLocalORMSession.flush_all()
        ThreadLocalORMSession.close_all()
        self.check_configure()
        ThreadLocalORMSession.close_all()

    def set_context(self, rcpt):
        if rcpt == self.nick:
            return False
        chan = self.channels.get(rcpt, None)
        if not chan:
            return False
        h.set_context(chan.project_id,
                      app_config_id=chan.app_config_id)
        return True

    def handle_shortlink(self, lnk, sender, rcpt):
        art = lnk.ref.artifact
        if security.has_access(art, 'read', user=M.User.anonymous())():
            index = art.index()
            text = index['snippet_s'] or h.get_first(index, 'title')
            url = urljoin(
                tg.config['base_url'], index['url_s'])
            self.notice(rcpt, f'[{lnk.link}] - [{text}]({url})')

    def log_channel(self, sender, cmd, rcpt, rest):
        if cmd not in ('NOTICE', 'PRIVMSG'):
            self.logger.debug('IGN: %s %s %s %s', sender, cmd, rcpt, rest)
            return
        if cmd == 'NOTICE':
            text = '--' + rest
        else:
            text = rest
        CM.ChatMessage(
            sender='!'.join(sender),
            channel=rcpt,
            text=text)
        ThreadLocalORMSession.flush_all()
        ThreadLocalORMSession.close_all()
