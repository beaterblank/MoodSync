"""Advertise the HTTP server through DNS-SD / Bonjour."""
import ipaddress
import logging
import os
import socket

from ifaddr import get_adapters
from zeroconf import IPVersion, ServiceInfo, Zeroconf
from zeroconf.asyncio import AsyncZeroconf

class LibraryAdvertisement:
    def __init__(self):
        self.zeroconf = None
        self.info = None

    async def start(self):
        await self.stop()
        host = os.getenv("MOODSYNC_HOST", "0.0.0.0")
        addresses = []
        for adapter in get_adapters():
            for address in adapter.ips:
                if not isinstance(address.ip, str):
                    continue
                ip = ipaddress.ip_address(address.ip)
                if ip.version == 4 and not ip.is_loopback and (host == "0.0.0.0" or host == str(ip)):
                    addresses.append(ip.packed)
        if not addresses:
            logging.warning("Bonjour: no reachable LAN address for the configured host")
            return
        name = os.getenv("MOODSYNC_SERVER_NAME", "My music library").replace(".", "-")[:40]
        hostname = socket.gethostname().split(".")[0]
        self.info = ServiceInfo(
            "_moodsync._tcp.local.", f"{name}._moodsync._tcp.local.",
            addresses=addresses, port=int(os.getenv("MOODSYNC_PORT", "8088")),
            properties={"service": "moodsync", "version": "1", "path": "/api/device/health"},
            server=f"{hostname}.local.",
        )

        self.zeroconf = AsyncZeroconf()

        try:
            await self.zeroconf.async_register_service(self.info, allow_name_change=True)
            logging.info("MoodSync advertised via Bonjour")
        except Exception:
            logging.exception("Could not advertise MoodSync with Bonjour")
            await self.stop()

    async def stop(self):
        if self.zeroconf:
            try:
                await self.zeroconf.async_close()
            finally:
                self.zeroconf = None


advertisement = LibraryAdvertisement()
