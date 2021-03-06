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
import hashlib
import random
import socket
import threading
import time
import traceback


COUNTER, COUNTER_LOCK = random.randint(0, 0xffffff), threading.Lock()
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
  uid = '%d-%8.8x' % (time.time(), COUNTER)
  COUNTER += 1
  COUNTER_LOCK.release()
  return uid

def md5hex(data):
  h1 = hashlib.md5()
  h1.update(data)
  return h1.hexdigest().lower()


class IrcClient:
  """This is a bare-bones IRC client which logs on and ping/pongs."""

  DEBUG = False

  server = None
  username = 'mutiny'
  nickname = 'Mutiny_%d' % random.randint(0, 1000)
  fullname = "Mutiny: Pirate Meeting Gateway"
  low_nick = '<unset>'
  profile = None
  log_id = None

  def __init__(self):
    self.partial = ''
    self.uid = get_unique_id()
    self.seen = time.time()

  def irc_nickname(self, nickname):
    self.nickname = str(nickname)
    self.low_nick = str(nickname).lower()
    return self

  def irc_fullname(self, fullname):
    self.fullname = str(fullname)
    return self

  def irc_username(self, username):
    self.username = str(username)
    return self

  def irc_channels(self, channels):
    self.channels = [str(c) for c in channels]
    return self

  def irc_profile(self, profile):
    self.profile = profile

    if 'nick' in profile:
      self.irc_nickname(profile['nick'])

    if 'uid' in profile:
      self.irc_username(md5hex(str(profile['uid']))[:8])

    user_info = ', '.join([profile.get('name', 'Anonymous'), profile.get('home', '')])
    while user_info.endswith(', '):
      user_info = user_info[:-2]
    if user_info:
      self.irc_fullname(user_info.encode('utf-8'))

    return self

  def process_connect(self, write_cb, fullname=None):
    """Process a new connection."""
    write_cb(('NICK %s\r\nUSER %s x x :%s\r\n'
              ) % (self.nickname, self.username, fullname or self.fullname))

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
      callback = getattr(self, 'on_%s' % parts[1].lower())
    except (IndexError, AttributeError, ValueError):
      print '%s' % parts
      return None
    try:
      return callback(parts, write_cb)
    except AttributeError:
      print '%s' % parts
      return None
    except:
      print '%s' % traceback.format_exc()
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
    self.nickname = parts[2]
    self.low_nick = parts[2].lower()

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
  def on_312(self, parts, write_cb): """User's server info."""
  def on_317(self, parts, write_cb): """Seconds idle, signon time."""
  def on_318(self, parts, write_cb): """End of /WHOIS list."""
  def on_332(self, parts, write_cb): """Channel topic."""
  def on_333(self, parts, write_cb): """Channel topic setter."""
  def on_366(self, parts, write_cb): """End of /NAMES list."""
  def on_372(self, parts, write_cb): """MOTD line."""
  def on_375(self, parts, write_cb): """Start of MOTD."""

  def on_376(self, parts, write_cb):
    """End of MOTD."""
    if self.channels:
      write_cb('JOIN %s\r\n' % '\r\nJOIN '.join(self.channels))

  def on_396(self, parts, write_cb): """Hidden host."""

  def on_433(self, parts, write_cb):
    """Nickname already in use, generate another one."""
    if self.nickname.endswith('_'):
      self.irc_nickname(self.nickname[:-1]+'-')
    elif self.nickname.endswith('-'):
      self.irc_nickname(self.nickname[:-1]+'1')
    elif self.nickname.endswith('1'):
      self.irc_nickname(self.nickname[:-1]+'2')
    elif self.nickname.endswith('2'):
      self.irc_nickname(self.nickname[:-1]+'3')
    else:
      self.irc_nickname(self.nickname+'_')
    if len(self.nickname) > 15:
      self.irc_nickname(self.nickname[:10]+self.nickname[-1])
    write_cb('NICK %s\r\n' % self.nickname)

  def on_671(self, parts, write_cb): """Is using a secure connection."""

  def on_error(self, parts, write_cb):
    print 'ERROR: %s' % parts
    write_cb('QUIT\r\n')

  def on_join(self, parts, write_cb): """User JOINed."""
  def on_notice(self, parts, write_cb): """Bots must ignore NOTICE messages."""
  def on_part(self, parts, write_cb): """User dePARTed."""

  def on_ping(self, parts, write_cb):
    write_cb('PONG %s\r\n' % parts[2])

  def on_privmsg(self, parts, write_cb):
    if parts[2].lower() == self.low_nick:
      return self.on_privmsg_self(parts, write_cb)
    elif parts[2] in self.channels:
      if parts[3].strip().lower().startswith('%s:' % self.low_nick):
        self.on_privmsg_self(parts, write_cb)
      return self.on_privmsg_channel(parts, write_cb)

  def on_privmsg_self(self, parts, write_cb):
    fromnick = parts[0].split('!', 1)[0]
    write_cb(('NOTICE %s '
              ':Sorry, my client does not support private messages.\r\n'
              ) % fromnick)

  def on_privmsg_channel(self, parts, write_cb): """Messages to channels."""

# def on_quit(self, parts, write_cb): """User QUIT."""


class IrcLogger(IrcClient):
  """This client logs what he sees."""

  MAXLINES = 200

  def __init__(self):
    IrcClient.__init__(self)
    self.logs = {}
    self.want_whois = []
    self.whois_data = {}
    self.whois_cache = {}
    self.channel_mode = {}
    self.watchers = {}
    self.users = {}

  def irc_find_user(self, nickname=None, log_id=None):
    try:
      nickname = nickname.lower()
      user = None
      for uid, user in self.users.iteritems():
        if ((nickname and (user.low_nick == nickname)) or
            (log_id and (user.log_id == log_id))):
          return user
    except (ValueError, KeyError):
      pass
    return None

  def irc_augment_whois(self, nickname, user):
    if user:
      return {
        'realname': user.profile['name'].encode('utf-8'),
        'userinfo': user.profile['home'].encode('utf-8'),
        'avatar': user.profile['pic'].encode('utf-8'),
        'url': user.profile['url'].encode('utf-8')
      }
    else:
      return {
        'avatar': '/_skin/avatar_%s.jpg' % md5hex(nickname)[0]
      }

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

  def irc_channel_log_append(self, channel, data):
    self.irc_channel_log(channel).append(data)
    self.irc_notify_watchers(channel)

  def irc_whois(self, nick, write_cb):
    write_cb('WHOIS %s\r\n' % nick)
    try:
      while True:
        self.want_whois.remove(nick)
    except ValueError:
      pass

  def irc_channel_users(self, channel):
    users = {}
    for ts, info in irc.channel_log(channel):
      if 'nick' in info:
        nick = info['nick']
        event = info.get('event')
        if event == 'whois':
          users[nick] = info
        elif event in ('part', 'quit') and nick in users:
          del users[nick]
    return users

  def irc_whois_info(self, nick):
    if nick not in self.whois_data:
      self.whois_data[nick] = {
        'event': 'whois',
        'nick': nick
      }
    return self.whois_data[nick]

  def irc_cached_whois(self, nickname, userhost=None):
    nuh = '%s!%s' % (nickname, userhost)
    if userhost and nuh in self.whois_cache:
      return self.whois_cache[nuh]
    info = {'uid': ''}
    for nuh in self.whois_cache:
      n_info = self.whois_cache[nuh]
      if n_info['uid'] > info['uid']:
        info = n_info
    return info

  def irc_update_whois(self, nuh, update={}, depart=None, new_nick=None):
    nickname, userhost = nuh.split('!', 1)
    whois = self.irc_cached_whois(nickname, userhost)
    channels = [c for c in whois.get('channels', []) if c in self.channels]
    if whois['uid']:
      if new_nick:
        whois['nick'] = new_nick
        self.whois_cache['%s!%s' % (new_nick, userhost)] = whois
        if nuh in self.whois_cache:
          del self.whois_cache[nuh]
      whois.update(update)
      if depart and 'channels' in whois:
        whois['channels'].remove(depart)
      for channel in channels:
        if whois:
          self.irc_channel_log_append(channel, [get_timed_uid(), whois])
    return whois, channels

  def irc_parsed_mode(self, channel):
    mode_string, log_id, fixme = self.channel_mode.get(channel, ['ns', 0, None])
    mode_words = mode_string.split(' ')
    mode = mode_words.pop(0)
    info = {
      'event': 'mode',
      'log_id': log_id,
      'raw_mode': mode_string
    }
    for m in mode:
      if m == 'a':
        info['anonymous'] = True
      elif m == 'b':
        info['bans'] = info.get('bans', []) + [mode_words.pop(0)]
      elif m == 'i':
        info['invite_only'] = True
      elif m == 'I':
        info['invite_mask'] = info.get('invite_mask', []) + [mode_words.pop(0)]
      elif m == 'k':
        info['key'] = mode_words.pop(0)
      elif m == 'l':
        info['limit'] = mode_words.pop(0)
      elif m == 'm':
        info['moderated'] = True
      elif m == 'n':
        info['must_join'] = True
      elif m == 'q':
        info['quiet'] = True
      elif m == 's':
        info['secret'] = True
      elif m == 't':
        info['topic_locked'] = True
    return info

  ### Protocol callbacks follow ###

  def on_324(self, parts, write_cb):
    """Channel mode information."""
    channel, mode = parts[3], parts[4]
    log_id = get_timed_uid()
    self.channel_mode[channel] = [mode, log_id, None]
    self.irc_channel_log_append(channel,
                                [log_id, self.irc_parsed_mode(channel)])

  def on_mode(self, parts, write_cb):
    by_nuh, channel, mode = parts[0], parts[2], parts[3]
    if '!' in by_nuh:
      nickname, userhost = by_nuh.split('!', 1)
      self.irc_channel_log_append(channel, [get_timed_uid(), {
        'event': 'mode',
        'mode': mode,
        'nick': nickname,
        'uid': self.irc_cached_whois(nickname, userhost).get('uid')
      }])
      write_cb('MODE %s\r\n' % channel)
    else:
      return IrcClient.on_mode(self, parts, write_cb)

  def on_353(self, parts, write_cb):
    """We want more info about anyone listed in /NAMES."""
    self.want_whois.extend(parts[5].replace('@', '')
                                   .replace('+', '').split())

  def on_366(self, parts, write_cb):
    """On end of /NAMES, run /MODE and /WHOIS to gather channel info."""
    channel = parts[3]
    write_cb('MODE %s\r\n' % channel)
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
    """On end of /WHOIS, record result, ask for more."""
    nickname = parts[3]
    info = self.irc_whois_info(nickname)
    del self.whois_data[nickname]

    nuh = '%s!%s' % (nickname, info['userhost'])
    new_uid = get_timed_uid()
    info['uid'] = self.whois_cache.get(nuh, {}).get('uid', new_uid)
    self.whois_cache[nuh] = info

    # Do we know this user, can we augment with profile data?
    user = self.irc_find_user(nickname, info['uid'])
    info.update(self.irc_augment_whois(nickname, user))

    # Write back the log ID
    if user:
      user.log_id = info['uid']

    if nickname.lower() != self.low_nick:
      for channel in info.get('channels', []):
        if channel in self.channels:
          self.irc_channel_log_append(channel, [new_uid, info])

    if self.want_whois:
      self.irc_whois(self.want_whois.pop(0), write_cb)

  def on_332(self, parts, write_cb):
    """Channel topic."""
    channel, topic = parts[3], parts[4]
    info = {
      'event': 'topic',
      'text': topic,
    }
    log = self.irc_channel_log(channel);
    if log:
      last_id, last = log[-1]
      if last.get('event') == 'topic' and not last.get('text'):
        info.update(last)
        info['update'] = last_id
    self.irc_channel_log_append(channel, [get_timed_uid(), info])

  def on_333(self, parts, write_cb):
    """Channel topic metadata."""
    channel, by_nuh, when = parts[3], parts[4], parts[5]
    nickname, userhost = by_nuh.split('!', 1)
    info = {
      'event': 'topic',
      'nick': nickname,
      'uid': self.irc_cached_whois(nickname, userhost).get('uid')
    }
    log = self.irc_channel_log(channel);
    if log:
      last_id, last = log[-1]
      if last.get('event') == 'topic' and not last.get('nick'):
        info.update(last)
        info['update'] = last_id
    self.irc_channel_log_append(channel, [get_timed_uid(), info])

  def on_join(self, parts, write_cb):
    nickname, userhost = parts[0].split('!', 1)
    if nickname.lower() != self.low_nick:
      self.irc_channel_log_append(parts[2], [get_timed_uid(), {
        'event': 'join',
        'nick': nickname,
        'uid': self.irc_cached_whois(nickname, userhost).get('uid')
      }])
      self.irc_whois(nickname, write_cb)

  def on_nick(self, parts, write_cb):
    nuh, new_nick = parts[0], parts[2]
    nickname, userhost = nuh.split('!', 1)
    whois, channels = self.irc_update_whois(nuh, new_nick=new_nick)
    for channel in channels:
      self.irc_channel_log_append(channel, [get_timed_uid(), {
        'event': 'nick',
        'nick': nickname,
        'text': new_nick,
        'uid': whois.get('uid')
      }])

  def on_part(self, parts, write_cb):
    nuh, channel = parts[0], parts[2]
    nickname, userhost = nuh.split('!', 1)
    whois, channels = self.irc_update_whois(nuh, depart=channel)
    self.irc_channel_log_append(channel, [get_timed_uid(), {
      'event': 'part',
      'nick': nickname,
      'uid': self.irc_cached_whois(nickname, userhost).get('uid')
    }])

  def on_privmsg_channel(self, parts, write_cb):
    nickname, userhost = parts[0].split('!', 1)
    msg_type, text = self.irc_decode_message(parts[3])
    self.irc_channel_log_append(parts[2], [get_timed_uid(), {
      'event': msg_type,
      'text': text,
      'nick': nickname,
      'uid': self.irc_cached_whois(nickname, userhost).get('uid')
    }])

  def on_quit(self, parts, write_cb):
    nuh, quit_msg = parts[0], parts[2]
    nickname, userhost = nuh.split('!', 1)
    whois, channels = self.irc_update_whois(nuh, update={'channels': []})
    for channel in channels:
      self.irc_channel_log_append(channel, [get_timed_uid(), {
        'event': 'quit',
        'nick': nickname,
        'text': quit_msg,
        'uid': whois.get('uid')
      }])

  def on_topic(self, parts, write_cb):
    nickname, userhost = parts[0].split('!', 1)
    self.irc_channel_log_append(parts[2], [get_timed_uid(), {
      'event': 'topic',
      'text': parts[3],
      'nick': nickname,
      'uid': self.irc_cached_whois(nickname, userhost).get('uid')
    }])



class IrcBot(IrcLogger):
  """This client logs what he sees and is very helpful."""

  def on_privmsg_self(self, parts, write_cb):
    fromnick = parts[0].split('!', 1)[0]
    message = parts[3].strip()
    if message.lower().startswith('%s:' % self.low_nick):
      message = message[len(self.nickname)+1:]
    if parts[2].lower() != self.nickname:
      channel = parts[2]
    else:
      channel = None
    parts = message.split()
    try:
      callback = getattr(self, 'cmd_%s' % parts[0].lower())
    except (IndexError, AttributeError):
      return None
    try:
      return callback(fromnick, channel, parts, write_cb)
    except:
      print '%s' % traceback.format_exc()
      return None

  def cmd_ping(self, fromnick, channel, parts, write_cb):
    write_cb('NOTICE %s :pongalong!\r\n' % fromnick)


if __name__ == "__main__":
  # Test things?
  pass
