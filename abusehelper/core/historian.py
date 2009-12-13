import sqlite3
import time
from idiokit.xmpp import connect, Element
from idiokit.jid import JID
from idiokit import threado, timer
from abusehelper.core import roomfarm, events, services

class HistoryDB(threado.GeneratorStream):
    def __init__(self, path=None, keeptime=None):
        threado.GeneratorStream.__init__(self)

        if path is None:
            path = ":memory:"
        self.conn = sqlite3.connect(path)

        cursor = self.conn.cursor()

        cursor.execute("CREATE TABLE IF NOT EXISTS events "+
                       "(id INTEGER PRIMARY KEY, timestamp INTEGER, room INTEGER)")
        cursor.execute("CREATE INDEX IF NOT EXISTS events_id_index ON events(id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS events_room_ts_index ON events(room, timestamp)")
        cursor.execute("CREATE INDEX IF NOT EXISTS events_room_index ON events(room)")
        cursor.execute("CREATE INDEX IF NOT EXISTS events_ts_index ON events(timestamp)")
        
        cursor.execute("CREATE TABLE IF NOT EXISTS attrs "+
                       "(eventid INTEGER, key TEXT, value TEXT)")
        cursor.execute("CREATE INDEX IF NOT EXISTS attrs_eventid_index ON attrs(eventid)")

        self.conn.commit()
        self.keeptime = keeptime
        self.cursor = self.conn.cursor()

        self.start()

    def collect(self, room_name):
        collect = self._collect(room_name)
        services.bind(self, collect)
        return collect

    @threado.stream_fast
    def _collect(inner, self, room_name):
        while True:
            yield inner
                
            for event in inner:
                self.cursor.execute("INSERT INTO events(timestamp, room) VALUES (?, ?)",
                                    (int(time.time()), room_name))
                eventid = self.cursor.lastrowid
        
                for key, values in event.attrs.items():
                    self.cursor.executemany("INSERT INTO attrs(eventid, key, value) VALUES (?, ?, ?)",
                                            [(eventid, key, value) for value in values])

    def run(self, interval=1.0):
        try:
            while True:
                yield self.inner.sub(timer.sleep(interval))
                list(self.inner)

                if self.keeptime is not None:
                    cutoff = int(time.time() - self.keeptime)
                    
                    max_id = self.cursor.execute("SELECT MAX(events.id) FROM events "+
                                                 "WHERE events.timestamp <= ?", (cutoff,))
                    
                    max_id = list(max_id)[0][0]
                    if max_id is not None:
                        self.cursor.execute("DELETE FROM events WHERE events.id <= ?",
                                            (max_id,))
                        self.cursor.execute("DELETE FROM attrs WHERE attrs.eventid <= ?",
                                            (max_id,))
                self.conn.commit()
                self.cursor = self.conn.cursor()
        finally:
            self.conn.commit()
            self.conn.close()

    def close(self):
        self.throw(threado.Finished())

    def find(self, room_name=None, start=None, end=None):
        query = ("SELECT events.id, events.room, events.timestamp, attrs.key, attrs.value "+
                 "FROM attrs "+
                 "INNER JOIN events ON events.id=attrs.eventid ")
        args = list()
        where = list()
    
        if room_name is not None:
            where.append("events.room = ?")
            args.append(room_name)

        if None not in (start, end):
            where.append("events.timestamp BETWEEN ? AND ?")
            args.append(start)
            args.append(end)
        elif start is not None:
            where.append("events.timestamp >= ?")
            args.append(start)
        elif end is not None:
            where.append("events.timestamp < ?")
            args.append(end)

        if where:
            query += "WHERE " + " AND ".join(where) + " "
        
        query += "ORDER BY events.id"

        event = events.Event()
        previous_id = None
        previous_ts = None
        previous_room = None
        for id, room, ts, key, value in self.conn.execute(query, args):
            if previous_id != id:
                if previous_id is not None:
                    yield previous_ts, previous_room, event
                event = events.Event()

            previous_id = id
            previous_ts = ts
            previous_room = room

            event.add(key, value)

        if previous_id is not None:
            yield previous_ts, previous_room, event

def format_time(timestamp):
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(timestamp))

def parse_command(message, name):
    parts = message.text.split()
    if not len(parts) >= 2:
        return None
    command = parts[0][1:]
    if command != name:
        return None

    keyed = dict()
    values = set()
    for part in parts[1:]:
        pair = part.split("=")
        if len(pair) >= 2:
            keyed.setdefault(pair[0], set())
            keyed[pair[0]].add(pair[1])
        elif len(pair) == 1:
            values.add(pair[0])

    def _match(event):
        for event_key, event_values in event.attrs.iteritems():
            if event_values & values:
                return True
            if event_values & keyed.get(event_key, set()):
                return True
        return False
    return _match

class HistorianSession(services.Session):
    def __init__(self, service):
        services.Session.__init__(self)
        self.service = service

    @threado.stream
    def config(inner, self, conf):
        if conf:
            self.service.rooms(self, *conf['rooms'])
        else:
            self.service.rooms(self)
        yield
        inner.finish(conf)

class HistorianService(roomfarm.RoomFarm):
    def __init__(self, xmpp, db_file):
        roomfarm.RoomFarm.__init__(self, xmpp)
        self.db = HistoryDB(db_file)

    @threado.stream
    def handle_room(inner, self, name):
        room = yield inner.sub(self.xmpp.muc.join(name))

        yield inner.sub(room
                        | self.command_parser(room)
                        | events.stanzas_to_events()
                        | self.db.collect(unicode(room.room_jid))
                        | threado.throws())

    def session(self):
        return HistorianSession(self)

    @threado.stream_fast
    def command_parser(inner, self, room):
        while True:
            yield inner

            for elements in inner:
                inner.send(elements)

                for message in elements.named("message").with_attrs("from"):
                    sender = JID(message.get_attr("from"))
                    if sender == room.nick_jid:
                        continue

                    for body in message.children("body"):
                        matcher = parse_command(body, "historian")
                        if matcher is None:
                            continue

                        print "Got command", repr(body.text)
                        rjid = unicode(room.room_jid)
                        
                        for etime, eroom, event in self.db.find(rjid):
                            yield

                            if not matcher(event):
                                continue

                            body = Element("body")
                            body.text = "%s %s\n" % (format_time(etime), eroom)
                            for event_key, event_values in event.attrs.items():
                                vals = ", ".join(event_values)
                                body.text += "%s: %s\n" % (event_key, vals)
                            room.send(body)

def main(xmpp_jid, service_room, 
         db_file=None, xmpp_password=None, log_file=None):
    import getpass
    from abusehelper.core import log

    if not xmpp_password:
        xmpp_password = getpass.getpass("XMPP password: ")

    logger = log.config_logger("historian", filename=log_file)

    @threado.stream
    def bot(inner):
        print "Connecting XMPP server with JID", xmpp_jid
        xmpp = yield connect(xmpp_jid, xmpp_password)
        xmpp.core.presence()

        print "Joining lobby", service_room
        lobby = yield services.join_lobby(xmpp, service_room, "historian")

        service = HistorianService(xmpp, db_file)
        yield inner.sub(lobby.offer("historian", service))
    return bot()
main.service_room_help = "the room where the services are collected"
main.xmpp_jid_help = "the XMPP username (e.g. user@xmpp.example.com)"
main.xmpp_password_help = "the XMPP password"
main.db_file_help = ("write the history data into the given file "+
                     "(default: keep the history only in memory)")
main.log_file_help = "log to the given file instead of the console"

if __name__ == "__main__":
    from abusehelper.core import opts
    threado.run(opts.optparse(main))