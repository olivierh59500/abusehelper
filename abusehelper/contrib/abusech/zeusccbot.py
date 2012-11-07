"""
abuse.ch Zeus C&C RSS feed bot.

Maintainer: Lari Huttunen <mit-code@huttu.net>
"""
import re
import socket
from abusehelper.core import bot, events
from abusehelper.contrib.rssbot.rssbot import RSSBot


class ZeusCcBot(RSSBot):
    feeds = bot.ListParam(default=["https://zeustracker.abuse.ch/rss.php"])
    # If treat_as_dns_source is set, the feed ip is dropped.
    treat_as_dns_source = bot.BoolParam()

    def is_ip(self, string):
        for addr_type in (socket.AF_INET, socket.AF_INET6):
            try:
                socket.inet_pton(addr_type, string)
            except (ValueError, socket.error):
                pass
            else:
                return True
        return False

    def resolve_level(self, v):
        levels = {
            "1": "bulletproof hosted",
            "2": "hacked webserver",
            "3": "free hosting service",
            "4": "unknown",
            "5": "hosted on a fastflux botnet"
        }
        return levels[v]

    def create_event(self, **keys):
        event = events.Event()
        # handle link data
        link = keys.get("link", None)
        if link:
            event.add("description url", link)
        # handle title data
        title = keys.get("title", None)
        if title:
            t = []
            t = title.split()
            host = t[0]
            date = " ".join(t[1:])
            if self.is_ip(host):
                event.add("ip", host)
            else:
                event.add("host", host)
            br = re.compile('[()]')
            date = br.sub('', date)
            date = date + " UTC"
            event.add("source time", date)
        # handle description data
        description = keys.get("description", None)
        if description:
            for part in description.split(","):
                pair = part.split(":", 1)
                if len(pair) < 2:
                    continue
                key = pair[0].strip()
                value = pair[1].strip()
                if not key or not value:
                    continue
        # handle description data
        description = keys.get("description", None)
        if description:
            for part in description.split(","):
                pair = part.split(":", 1)
                if len(pair) < 2:
                    continue
                key = pair[0].strip()
                value = pair[1].strip()
                if not key or not value:
                    continue
                if key == "Status":
                    event.add(key.lower(), value)
                elif key == "level":
                    level = self.resolve_level(value)
                    if level and level != "unknown":
                        event.add("description", level)
                elif key == "SBL" and value != "Not listed":
                    key = key.lower() + " id"
                    event.add(key, value)
                elif key == "IP address":
                    if not self.treat_as_dns_source:
                        event.add("ip", value)
        event.add("feed", "abuse.ch")
        event.add("malware", "ZeuS")
        event.add("type", "c&c")
        return event

if __name__ == "__main__":
    ZeusCcBot.from_command_line().execute()
