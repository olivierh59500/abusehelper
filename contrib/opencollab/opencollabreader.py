import random
import getpass
import hashlib

import idiokit
from idiokit import timer, threadpool
from abusehelper.core import bot, events
from opencollab import wiki

def normalize(value):
    if value.startswith("[[") and value.endswith("]]"):
        return value[2:-2]
    return value

class OpenCollabReader(bot.FeedBot):
    poll_interval = bot.IntParam(default=60)

    collab_url = bot.Param()
    collab_user = bot.Param()
    collab_password = bot.Param(default=None)
    collab_ignore_cert = bot.BoolParam()
    collab_extra_ca_certs = bot.Param(default=None)

    def __init__(self, *args, **keys):
        bot.FeedBot.__init__(self, *args, **keys)

        self.collab = wiki.GraphingWiki(self.collab_url,
            ssl_verify_cert=not self.collab_ignore_cert,
            ssl_ca_certs=self.collab_extra_ca_certs)

        if self.collab_password is None:
            self.collab_password = getpass.getpass("Collab password: ")
        self.collab.authenticate(self.collab_user, self.collab_password)

    def feed_keys(self, query, **keys):
        yield (query,)

    @idiokit.stream
    def feed(self, query):
        salt = str(random.randint(2**31, 2**32))

        def page_id(page):
            return hashlib.md5(page.encode("utf8") + salt).hexdigest()

        token = None
        current = dict()
        yield timer.sleep(5)
        while True:
            try:
                result = yield threadpool.thread(self.collab.request,
                                                 "IncGetMeta", query, token)
            except Exception, exc:
                self.log.error("IncGetMeta failed: %s" % exc)
            else:
                incremental, token, (removed, updates) = result
                removed = set(removed)
                if not incremental:
                    removed.update(current)
                    current.clear()

                for page, keys in updates.iteritems():
                    event = current.setdefault(page, events.Event())
                    event.add("id", page_id(page))
                    event.add("gwikipagename", page)

                    removed.discard(page)

                    for key, (discarded, added) in keys.iteritems():
                        for value in map(normalize, discarded):
                            event.discard(key, value)

                        for value in map(normalize, added):
                            event.add(key, value)
                    yield idiokit.send(event)

                for page in removed:
                    current.pop(page, None)

                    event = events.Event()
                    event.add("id", page_id(page))

                    yield idiokit.send(event)

            yield timer.sleep(self.poll_interval)

if __name__ == "__main__":
    OpenCollabReader.from_command_line().execute()
