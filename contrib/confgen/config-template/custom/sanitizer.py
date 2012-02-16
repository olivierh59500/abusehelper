import socket
import time as _time
import idiokit
from abusehelper.core import events, bot, taskfarm, services

def format_time(time_tuple=None):
    if time_tuple is None:
        time_tuple = _time.gmtime()
    return _time.strftime("%Y-%m-%d %H:%M:%S UTC", time_tuple)

def time(string, format="%Y-%m-%d %H:%M:%S"):
    try:
        parsed = _time.strptime(string, format)
    except ValueError:
        return None

    if _time.gmtime() < parsed:
        return None
    return format_time(parsed)

def ip(string):
    try:
        socket.inet_pton(socket.AF_INET, string)
    except socket.error:
        try:
            socket.inet_pton(socket.AF_INET6, string)
        except socket.error:
            return None
    return string

class Sanitizer(bot.ServiceBot):
    def __init__(self, **keys):
        bot.ServiceBot.__init__(self, **keys)
        self.rooms = taskfarm.TaskFarm(self.handle_room)
        self.srcs = taskfarm.Counter()

    @idiokit.stream
    def handle_room(self, name):
        self.log.info("Joining room %r", name)
        room = yield self.xmpp.muc.join(name, self.bot_name)
        self.log.info("Joined room %r", name)
        try:
            yield idiokit.pipe(events.events_to_elements(),
                               room,
                               events.stanzas_to_events(),
                               self.distribute(name))
        finally:
            self.log.info("Left room %r", name)

    @idiokit.stream
    def distribute(self, name):
        while True:
            event = yield idiokit.next()

            rooms = set(map(self.rooms.get, self.srcs.get(name)))
            rooms.discard(None)
            if not rooms:
                continue

            for sanitized_event in self.sanitize(event):
                for room in rooms:
                    yield room.send(sanitized_event)

    @idiokit.stream
    def session(self, _, src_room, dst_room, **keys):
        self.srcs.inc(src_room, dst_room)
        try:
            yield self.rooms.inc(src_room) | self.rooms.inc(dst_room)
        except services.Stop:
            idiokit.stop()
        finally:
            self.srcs.dec(src_room, dst_room)

    def sanitize(self, event):
        return [event]
