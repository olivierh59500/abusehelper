"""
Read 'mr: ip=ptr, ip=cymru, name=a, name=aaaa,   
name=mx, name=soa, name=xmpp, name=stun' 
style messages from a messgae body, resolve those 
through mresolve and return resolved triplets
in a similar message which includes machine readable
idiokit namespace.
"""
from idiokit import threado
from abusehelper.core import events
from idiokit import jid
from abusehelper.core import bot
import re, IPy, subprocess
from subprocess import Popen


class MrBot(bot.XMPPBot):
    """
    MrBot implmentation
    """
    # Define two parameters (in addition to the default XMPPBot ones)
    room = bot.Param("mr room")


    @threado.stream
    def main(inner, self):
        # Join the XMPP network using credentials given from the command line
        conn = yield self.xmpp_connect()

        # Join the XMPP rooms
        src = yield conn.muc.join(self.room, self.bot_name)

        self.log.info("Joined room %r.", self.room)

        # Forward body elements from the src room to the dst room
        # but filter away stuff by the bot itself to avoid nasty loops.
        own_jid = src.nick_jid
        yield inner.sub(src | self.mr(own_jid) | \
                            events.events_to_elements() | src )
    @threado.stream
    def mr(inner, self, own_jid):
        """Create idiokit events and filter own messages."""
        rtypes = set(['ipv4', 'ipv6', 'name', 'xmpp', 'stun', 'as', 'soa'])

        def resolveRequests(expanded,mresolve):
            mr = Popen(mresolve, shell=True, stdin=subprocess.PIPE,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, close_fds=1)
            for rr in expanded:
                mr.stdin.write(rr + '\n')
            (sout, err) = mr.communicate()
            return sout, err

        def expandRequest(rr, rtype):
            expanded = []
            if rtype == 'soa':
                expanded.append(rr + ';SOA')
            elif rtype == 'ipv4':
                expanded.append(rr + ';PTR')
                rev = re.split('\.', rr)
                rev.reverse()
                expanded.append('.'.join(rev) + ".origin.asn.cymru.com;TXT")
            elif rtype == 'ipv6':
                rev = []
                comprr = IPy.IP(rr).strCompressed()
                exprr = IPy.IP(rr).strFullsize()
                expanded.append(comprr + ";PTR")
                parts = re.split(':', exprr)
                for s in parts:
                    part = re.findall('[\d\w]', s)
                    part.reverse()
                    rev.append('.'.join(part))
                    rev.reverse()
                    addr = '.'.join(rev)
                expanded.append(addr + ".origin6.asn.cymru.com;TXT")
            elif rtype == 'as':
                expanded.append(rr.upper() + ".asn.cymru.com;TXT")
            elif rtype == 'name':
                expanded.append(rr + ";A")
                expanded.append(rr + ";AAAA")
                expanded.append(rr + ";MX")
                expanded.append(rr + ";SOA")
            elif rtype == 'xmpp':
                expanded.append("_xmpp-client._tcp." + rr + ";SRV")
                expanded.append("_xmpp-server._tcp." + rr + ";SRV")
                expanded.append("_jabber._tcp." + rr + ";SRV")
            elif rtype == 'stun':
                expanded.append("_sips._tcp." + rr + ";SRV")
                expanded.append("_sip._tcp." + rr + ";SRV")
                expanded.append("_sip._udp." + rr + ";SRV")
            return expanded

        while True:
            # Receive one XML element from the pipe input
            element = yield inner
            # Prevent endless feedback loops
            sender = jid.JID(element.get_attr("from"))
            if sender == own_jid:
                continue

            for body in element.named("message").children("body"):
                pieces = body.text.split()
                event = events.Event()
                if len(pieces) < 2 or pieces[0].lower() != "/resolve":
                    event.add('syntax', '/resolve rr type')
                else:
                    rr = pieces[1]
                    types = pieces[2:] or ['soa']
                    for rtype in types:
                        if rtype not in rtypes:
                            continue
                        expanded = expandRequest(rr, rtype)
                        answer,err = resolveRequests(expanded, '/usr/bin/mresolve')
                        event.add(rr, answer)
                inner.send(event)
                 
# Instantiate a MrBot from command line parameters and run it.
MrBot.from_command_line().run()
