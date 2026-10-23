"""Find Android TVs on the local network with mDNS. No IP address needed."""
import asyncio
import socket
from zeroconf import ServiceStateChange
from zeroconf.asyncio import AsyncServiceBrowser, AsyncZeroconf

# Android TV and Google TV announce this name on the network.
SERVICE = "_androidtvremote2._tcp.local."


async def discover(timeout=5.0, service=SERVICE):
    found = {}
    azc = AsyncZeroconf()

    async def resolve(name):
        info = await azc.async_get_service_info(service, name, 3000)
        if info and info.addresses:
            ip = socket.inet_ntoa(info.addresses[0])
            found[name] = (name.split(".")[0], ip, info.port)

    def on_change(zeroconf, service_type, name, state_change):
        if state_change is ServiceStateChange.Added:
            asyncio.ensure_future(resolve(name))

    browser = AsyncServiceBrowser(azc.zeroconf, service, handlers=[on_change])
    await asyncio.sleep(timeout)
    await browser.async_cancel()
    await azc.async_close()
    return list(found.values())


# SSDP search targets -> brand. Roku and LG answer these; Samsung usually does too.
SSDP = {
    "roku:ecp": "roku",
    "urn:lge-com:service:webos-second-screen:1": "lg",
    "urn:samsung.com:device:RemoteControlReceiver:1": "samsung",
}
# mDNS services -> brand (Samsung TVs advertise this one).
MDNS = {SERVICE: "android", "_samsungmsf._tcp.local.": "samsung"}


def _local_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))
        return s.getsockname()[0]
    except OSError:
        return "0.0.0.0"
    finally:
        s.close()


async def _ssdp(timeout):
    """Multicast M-SEARCH for each target; return {ip: brand}."""
    found = {}
    loop = asyncio.get_running_loop()

    class Proto(asyncio.DatagramProtocol):
        def datagram_received(self, data, addr):
            text = data.decode("latin-1").lower()
            for target, brand in SSDP.items():
                if target.lower() in text:
                    found.setdefault(addr[0], brand)

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    sock.setblocking(False)
    try:
        # Send out of the Wi-Fi/LAN adapter, not whichever one Windows picks first.
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_IF, socket.inet_aton(_local_ip()))
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
    except OSError:
        pass
    transport, _ = await loop.create_datagram_endpoint(Proto, sock=sock)
    try:
        for target in SSDP:
            msg = ("M-SEARCH * HTTP/1.1\r\nHOST: 239.255.255.250:1900\r\n"
                   f'MAN: "ssdp:discover"\r\nMX: 2\r\nST: {target}\r\n\r\n').encode()
            transport.sendto(msg, ("239.255.255.250", 1900))
        await asyncio.sleep(timeout)
    finally:
        transport.close()
    return found


async def _mdns(timeout):
    """Browse every MDNS service at once; return {ip: (brand, name)}."""
    found = {}
    azc = AsyncZeroconf()

    async def resolve(service, name):
        info = await azc.async_get_service_info(service, name, 3000)
        if info and info.addresses:
            found[socket.inet_ntoa(info.addresses[0])] = (MDNS[service], name.split(".")[0])

    def on_change(zeroconf, service_type, name, state_change):
        if state_change is ServiceStateChange.Added:
            asyncio.ensure_future(resolve(service_type, name))

    browsers = [AsyncServiceBrowser(azc.zeroconf, s, handlers=[on_change]) for s in MDNS]
    await asyncio.sleep(timeout)
    for b in browsers:
        await b.async_cancel()
    await azc.async_close()
    return found


async def discover_all(timeout=5.0):
    """Find TVs of every supported brand: [{"brand", "name", "ip"}, ...]."""
    mdns, ssdp = await asyncio.gather(_mdns(timeout), _ssdp(timeout))
    tvs = {ip: {"brand": brand, "name": name, "ip": ip} for ip, (brand, name) in mdns.items()}
    for ip, brand in ssdp.items():
        tvs.setdefault(ip, {"brand": brand, "name": None, "ip": ip})
    return list(tvs.values())


if __name__ == "__main__":
    tvs = asyncio.run(discover_all())
    if not tvs:
        print("No TV found. Check that the phone/computer and TV share one Wi-Fi network.")
    for tv in tvs:
        print(f"{tv['brand']:8} {tv['ip']:16} {tv['name'] or ''}")
