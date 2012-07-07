#!/usr/bin/python
#
# Mutiny.py, Copyright 2012, Bjarni R. Einarsson <http://bre.klaki.net/>
#
# This is an IRC-to-WWW gateway designed to help Pirates have Meetings.
#
################################################################################
#
# This program is free software: you can redistribute it and/or modify it under
# the terms of the  GNU  Affero General Public License as published by the Free
# Software Foundation, either version 3 of the License, or (at your option) any
# later version.
#
# This program is distributed in the hope that it will be useful,  but  WITHOUT
# ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
# FOR A PARTICULAR PURPOSE.  See the GNU Affero General Public License for more
# details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see: <http://www.gnu.org/licenses/>
#
################################################################################
#
# Python standard
import random
import socket
import threading
import time
import traceback


COUNTER, COUNTER_LOCK = 0, threading.Lock()
def get_unique_id():
  global COUNTER, COUNTER_LOCK
  COUNTER_LOCK.acquire()
  uid = '%x-%x' % (random.randint(0, 0x7fffffff), COUNTER)
  COUNTER += 1
  COUNTER_LOCK.release()
  return uid

def get_timed_uid():
  global COUNTER, COUNTER_LOCK
  COUNTER_LOCK.acquire()
  uid = '%d-%x' % (time.time(), COUNTER)
  COUNTER += 1
  COUNTER_LOCK.release()
  return uid


class IrcClient:
  """This is a bare-bones IRC client which logs on and ping/pongs."""

  DEBUG = False

  nickname = 'Mutiny_%d' % random.randint(0, 1000)
  fullname = "Mutiny: Pirate Meeting Gateway"

  def __init__(self):
    self.partial = ''
    self.uid = get_unique_id()

  def irc_nickname(self, nickname):
    self.nickname = nickname.lower()
    return self

  def irc_fullname(self, fullname):
    self.fullname = fullname
    return self

  def irc_channels(self, channels):
    self.channels = channels
    return self

  def process_connect(self, write_cb, fullname=None):
    """Process a new connection."""
    write_cb(('NICK %s\r\nUSER mutiny x x :%s\r\n'
              ) % (self.nickname, fullname or self.fullname))

  def process_data(self, data, write_cb):
    """Process data, presumably from a server."""
    lines = (self.partial+data).splitlines(True)
    if lines and not lines[-1].endswith('\n'):
      self.partial = lines.pop(-1)
    else:
      self.partial = ''

    for line in lines:
      self.process_line(line, write_cb)

  def process_line(self, line, write_cb):
    """IRC is line based, this routine process just one line."""
    try:
      parts = line.strip().split(' ', 1)
      if not line[0] == ':':
        parts[0:0] = ['']
      while (parts[-1][0] != ':') and (' ' in parts[-1]):
        parts[-1:] = parts[-1].split(' ', 1)
      for p in range(0, len(parts)):
        if parts[p] and parts[p][0] == ':':
          parts[p] = parts[p][1:]
      return getattr(self, 'on_%s' % parts[1].lower())(parts, write_cb)
    except (IndexError, AttributeError, ValueError):
      print '%s' % parts
      return None

  ### Protocol helpers ###

  def irc_decode_message(self, text, default='msg'):
    message = text
    if text[0] == '\x01' and text[-1] == '\x01':
      if text.lower().startswith('\x01action '):
        return 'act', text[8:-1]
      else:
        return 'ctcp', text[1:-1]
    else:
      return default, text

  ### Protocol callbacks follow ###

  def on_001(self, parts, write_cb):
    self.nickname = parts[2].lower()

  def on_002(self, parts, write_cb): """Server info."""
  def on_003(self, parts, write_cb): """Server uptime."""
  def on_004(self, parts, write_cb): """Mode characters."""
  def on_005(self, parts, write_cb): """Limits."""
  def on_250(self, parts, write_cb): """Max connection count."""
  def on_251(self, parts, write_cb): """Users visible/invisible on N servers."""
  def on_252(self, parts, write_cb): """IRCOPs online."""
  def on_254(self, parts, write_cb): """Channels."""
  def on_255(self, parts, write_cb): """Clients and servers."""
  def on_265(self, parts, write_cb): """Local user stats, current/max."""
  def on_266(self, parts, write_cb): """Global user stats, current/max."""
  def on_318(self, parts, write_cb): """End of /WHOIS list."""
  def on_366(self, parts, write_cb): """End of /NAMES list."""
  def on_372(self, parts, write_cb): """MOTD line."""
  def on_375(self, parts, write_cb): """Start of MOTD."""

  def on_376(self, parts, write_cb):
    """End of MOTD."""
    if self.channels:
      write_cb('JOIN %s\r\n' % '\r\nJOIN '.join(self.channels))

  def on_396(self, parts, write_cb): """Hidden host."""

  def on_error(self, parts, write_cb):
    print 'ERROR: %s' % parts
    write_cb('QUIT\r\n')

  def on_join(self, parts, write_cb): """Nick JOINed."""
  def on_notice(self, parts, write_cb): """Bots must ignore NOTICE messages."""
  #def on_part(self, parts, write_cb): """Nick dePARTed."""

  def on_ping(self, parts, write_cb):
    write_cb('PONG %s\r\n' % parts[2])

  def on_privmsg(self, parts, write_cb):
    if parts[2].lower() == self.nickname:
      return self.on_privmsg_self(parts, write_cb)
    elif parts[2] in self.channels:
      if parts[3].strip().lower().startswith('%s:' % self.nickname):
        return self.on_privmsg_self(parts, write_cb)
      return self.on_privmsg_channel(parts, write_cb)

  def on_privmsg_self(self, parts, write_cb):
    fromnick = parts[0].split('!', 1)[0]
    write_cb(('NOTICE %s '
              ':Sorry, my client does not support private messages.\r\n'
              ) % fromnick)

  def on_privmsg_channel(self, parts, write_cb): """Messages to channels."""


class IrcLogger(IrcClient):
  """This client logs what he sees."""

  MAXLINES = 200

  def __init__(self):
    IrcClient.__init__(self)
    self.logs = {}
    self.want_whois = []
    self.whois_data = {}
    self.watchers = {}

  def irc_channel_log(self, channel):
    if channel not in self.channels:
      return []
    if channel not in self.logs:
      self.logs[channel] = []
    else:
      while len(self.logs[channel]) > self.MAXLINES:
        self.logs[channel].pop(0)
    return self.logs[channel]

  def irc_watch_channel(self, channel, watcher):
    if channel not in self.watchers:
      self.watchers[channel] = [watcher]
    else:
      self.watchers[channel].append(watcher)

  def irc_notify_watchers(self, channel):
    watchers, self.watchers[channel] = self.watchers.get(channel, []), []
    now = time.time()
    for expire, cond, info in watchers:
      if now <= expire:
        cond.acquire()
        cond.notify()
        cond.release()

  def irc_log_merge(self, log, data):
    if log:
      log_id, log_info = log[-1]
      new_id, new_info = data
      delta = int(new_id.split('-')[0]) - int(log_id.split('-')[0])
      if ((delta < 15) and
          (log_info.get('nick', '') == new_info.get('nick', ''))):
        # Repeated join/part messages just zero each-other out.
        if ((new_info['event'] in ('join', 'part')) and
            (log_info['event'] in ('join', 'part')) and
            (new_info['event'] != log_info['event'])):
          log.pop(-1)
          new_info.update({
            'event': 'delete',
            'target': log_id
          })
          return [data]
        # Subsequent messages from the person get merged into one event.
        elif ((new_info['event'] == 'msg') and
              (log_info['event'] == 'msg')):
          if new_info['text'] != log_info['text']:
            new_info['text'] =  '\n'.join([log_info['text'], new_info['text']])
            return [[get_timed_uid(), {
              'event': 'delete',
              'target': log_id
            }], data]
          else:
            # ... or squelched if they are repeating themselves.
            return []
    return [data]

  def irc_channel_log_append(self, channel, data):
    log = self.irc_channel_log(channel)
    for line in self.irc_log_merge(log, data):
      log.append(line)
    self.irc_notify_watchers(channel)

  def irc_whois(self, nick, write_cb):
    write_cb('WHOIS %s\r\n' % nick)
    try:
      while True:
        self.want_whois.remove(nick)
    except ValueError:
      pass

  def irc_whois_info(self, nick):
    if nick not in self.whois_data:
      self.whois_data[nick] = {'event': 'whois', 'nick': nick}
    return self.whois_data[nick]

  def on_353(self, parts, write_cb):
    """We want more info about anyone listed in /NAMES."""
    self.want_whois.extend(parts[5].replace('@', '')
                                   .replace('+', '').split())

  def on_366(self, parts, write_cb):
    """On end of /NAMES, run /WHOIS for interesting peoples."""
    if self.want_whois:
      self.irc_whois(self.want_whois.pop(0), write_cb)

  def on_311(self, parts, write_cb):
    self.irc_whois_info(parts[3]).update({
      'userhost': '@'.join(parts[4:6]),
      'userinfo': parts[7],
    })

  def on_378(self, parts, write_cb):
    self.irc_whois_info(parts[3]).update({
      'realhost': parts[4]
    })

  def on_319(self, parts, write_cb):
    self.irc_whois_info(parts[3]).update({
      'channels': parts[4].replace('@', '').replace('+', '').split(),
      'chan_ops': [c.replace('@', '') for c in parts[4].split() if c[0] == '@'],
      'chan_vops': [c.replace('+', '') for c in parts[4].split() if c[0] == '+']
    })

  def on_318(self, parts, write_cb):
    """On end of /WHOIS, run /WHOIS for interesting peoples."""
    info = self.irc_whois_info(parts[3])
    for channel in info.get('channels', []):
      if channel in self.channels:
        self.irc_channel_log_append(channel, [get_timed_uid(), info])
    del self.whois_data[parts[3]]
    if self.want_whois:
      self.irc_whois(self.want_whois.pop(0), write_cb)
    IrcClient.on_318(self, parts, write_cb)

  def on_join(self, parts, write_cb):
    nickname = parts[0].split('!')[0]
    self.irc_channel_log_append(parts[2], [get_timed_uid(), {
      'event': 'join',
      'nick': nickname
    }])
    self.irc_whois(nickname, write_cb)

  def on_part(self, parts, write_cb):
    nickname = parts[0].split('!')[0]
    self.irc_channel_log_append(parts[2], [get_timed_uid(), {
      'event': 'part',
      'nick': nickname
    }])

  def on_privmsg_channel(self, parts, write_cb):
    nickname = parts[0].split('!')[0]
    msg_type, text = self.irc_decode_message(parts[3])
    self.irc_channel_log_append(parts[2], [get_timed_uid(), {
      'event': msg_type,
      'nick': nickname,
      'text': text
    }])


class IrcBot(IrcLogger):
  """This client logs what he sees and is very helpful."""

  def on_privmsg_self(self, parts, write_cb):
    fromnick = parts[0].split('!', 1)[0]
    message = parts[3].strip()
    if message.lower().startswith('%s:' % self.nickname):
      message = message[len(self.nickname)+1:]
    if parts[2].lower() != self.nickname:
      channel = parts[2]
    else:
      channel = None
    parts = message.split()
    try:
      return getattr(self, 'cmd_%s' % parts[0].lower()
                     )(fromnick, channel, parts, write_cb)
    except (IndexError, AttributeError):
      return None

  def cmd_ping(self, fromnick, channel, parts, write_cb):
    write_cb('NOTICE %s :pongalong!\r\n' % fromnick)


if __name__ == "__main__":
  # Test things?
  pass
