import couchdb.client
from idiokit import threado
from abusehelper.core import events

@threado.stream
def events_to_couchdb(inner, url, db_name):
    server = couchdb.client.Server(url)
    try:
        db = server.create(db_name)
    except couchdb.client.PreconditionFailed:
        db = server[db_name]

    while True:
        event = yield inner

        doc = dict()
        for key, values in event.attrs.items():
            doc[key] = list(values)
        db.create(doc)

def main():
    from idiokit.xmpp import XMPP

    xmpp = XMPP("user@example.com", "password")
    xmpp.connect()
    room = xmpp.muc.join("room@conference.example.com", "couchbot")

    pipeline = (room
                | events.stanzas_to_events()
                | events_to_couchdb("http://localhost:5984", "roomdb"))
    for _ in pipeline: pass

if __name__ == "__main__":
    main()