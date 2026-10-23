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


if __name__ == "__main__":
    tvs = asyncio.run(discover())
    if not tvs:
        print("No TV found. Check that the phone/computer and TV share one Wi-Fi network.")
    for name, ip, port in tvs:
        print(f"{name}  {ip}:{port}")
