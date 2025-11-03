import asyncio
import hashlib
import logging
from pathlib import Path
import socket

from aiodnsresolver import Resolver, TYPES
from dnslib import DNSRecord, QTYPE, RR, A, AAAA, RCODE, DNSQuestion
import yaml

from orbitlab.constants import DNS_ZONE_ROOT


class _DNSServerProtocol:
    def __init__(self, handler):
        self.handler = handler
        self._tasks = set()

    def connection_made(self, transport):
        self.transport = transport

    def datagram_received(self, data, addr):
        task = asyncio.create_task(self.handler(data, addr, self.transport))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)


class OrbitDNS:
    # TODO: load zones and upstreams from config
    def __init__(self, zones: dict[str, dict[str, str]], upstreams: list[str] | None = None):
        self.zones = zones
        self.upstreams = upstreams or ["1.1.1.1", "8.8.8.8"]
        self.resolve, self.clear_cache = Resolver()
        self.ttl = 60

    async def handle_query(self, data, addr, transport):
        try:
            request = DNSRecord.parse(data)
            reply = request.reply()
            for q in request.questions:
                q: DNSQuestion
                qname = str(q.qname).rstrip(".")
                qtype = QTYPE[q.qtype]

                # 1) Authoritative: exact match A/AAAA in local zones
                answered = await self._answer_authoritative(qname, qtype, reply)

                # 2) Forward (stub) for other names/types we support
                if not answered and qtype in ("A", "AAAA"):
                    try:
                        rec_type = TYPES.A if qtype == "A" else TYPES.AAAA
                        ip_addrs = await self.resolve(qname, rec_type)  # returns iterable of ipaddress objects
                        for ip in ip_addrs:
                            rdata = A(str(ip)) if qtype == "A" else AAAA(str(ip))
                            reply.add_answer(RR(qname, getattr(QTYPE, qtype), rdata=rdata, ttl=self.ttl))
                        answered = True
                    except Exception:
                        logging.exception("DNS resolution failed for %s (%s)", qname, qtype)

                if not answered:
                    reply.header.rcode = RCODE.NXDOMAIN
            transport.sendto(reply.pack(), addr)
        except (KeyError, AttributeError, ValueError):
            # If parsing fails, return FORMERR to be polite
            try:
                bad = DNSRecord.parse(data)
                r = bad.reply()
                r.header.rcode = RCODE.FORMERR
                transport.sendto(r.pack(), addr)
            except (KeyError, AttributeError, ValueError):
                logging.exception("DNS resolution failed during FORMERR handling")

    async def _answer_authoritative(self, qname: str, qtype: str, reply) -> bool:
        # Exact match first
        for zone, records in self.zones.items():
            if qname.endswith(zone):
                val = records.get(qname)
                if not val:
                    continue
                if ":" in val and qtype == "AAAA":
                    reply.add_answer(RR(qname, QTYPE.AAAA, rdata=AAAA(val), ttl=self.ttl))
                    return True
                if ":" not in val and qtype == "A":
                    reply.add_answer(RR(qname, QTYPE.A, rdata=A(val), ttl=self.ttl))
                    return True
        return False

    async def start(self, host: str = "0.0.0.0", port: int = 53) -> None:  # noqa: S104
        """Start the OrbitDNS server and runs indefinitely until cancelled.

        Args:
            host (str): The host/IP address to bind the server to (default is "0.0.0.0").
            port (int): The UDP port to listen on (default is 53).
        """
        loop = asyncio.get_running_loop()
        transport, _ = await loop.create_datagram_endpoint(
            lambda: _DNSServerProtocol(self.handle_query),
            local_addr=(host, port),
            family=socket.AF_INET,
            allow_broadcast=False,
            reuse_port=True
        )
        try:
            await asyncio.Future()
        finally:
            transport.close()


def file_hash(path: Path) -> str | None:
    try:
        h = hashlib.sha256()
        with path.open("rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
        return h.hexdigest()
    except FileNotFoundError:
        return None

async def watch_zones(dns: OrbitDNS, interval=1):
    # TODO: Update to watch all zone files in zone root
    last = None
    while True:
        try:
            cur = file_hash(path)
            if cur and cur != last:
                with open(path) as f:
                    dns.zones = yaml.safe_load(f) or {}
                last = cur
                print("[orbitdns] zones reloaded")
        except Exception as e:
            print("[orbitdns] watcher error:", e)
        await asyncio.sleep(interval)


async def main():
    zones = {}
    DNS_ZONE_ROOT.mkdir(parents=True, exist_ok=True)
    zone_config = DNS_ZONE_ROOT / "config.yaml"
    if zone_config.exists():
        with zone_config.open("rt") as f:
            zones = yaml.safe_load(f) or {}
    dns = OrbitDNS(zones)
    _ = asyncio.create_task(watch_zones(dns))
    await run_dns_server(dns, host="0.0.0.0", port=53)
