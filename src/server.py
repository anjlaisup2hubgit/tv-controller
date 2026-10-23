"""Phone-friendly web remote for Android TV, Roku, Samsung and LG TVs.

Run:  python server.py   then open the printed address on a phone that is on the
same Wi-Fi as the TV. discover.py finds TVs; drivers.py speaks each brand's protocol.
"""
import asyncio
import json
import os
import socket
from pathlib import Path

from discover import discover_all
from drivers import DRIVERS, Offline, Unsupported
import store

PORT = int(os.environ.get("PORT", 3000))
WEB = Path(__file__).parent / "web"

# Every button name the page can send; each driver maps these to its own protocol.
ALL_KEYS = set().union(*(d.KEYS for d in DRIVERS.values()))


class Tv:
    def __init__(self):
        self.driver = None
        self.found = []  # TVs seen by the last scan
        self.error = None
        self.state = "searching"  # searching | needs_pairing | pairing | ready | offline | disconnected
        self.lock = asyncio.Lock()
        self.watch = None

    def view(self):
        d = self.driver
        return {"state": self.state, "name": d.name if d else None, "brand": d.brand if d else None,
                "label": d.label if d else None, "pairing": d.pairing if d else None,
                "ip": d.ip if d else None, "error": self.error,
                "keys": sorted(d.KEYS) if d else None, "tvs": self.found}

    async def _drop(self):
        if self.watch:
            self.watch.cancel()
            self.watch = None
        if self.driver:
            await self.driver.close()
            self.driver = None

    async def connect(self, target=None):
        """Connect to `target` ({"brand", "ip"}), else the last-used TV, else the first TV found."""
        async with self.lock:
            await self._drop()
            self.state, self.error = "searching", None
            if target is None:
                self.found = await discover_all()
                target = store.get("last") or (self.found[0] if self.found else None)
            if not target or target.get("brand") not in DRIVERS:
                self.state = "offline"
                return
            known = next((t["name"] for t in self.found if t["ip"] == target["ip"]), None)
            self.driver = DRIVERS[target["brand"]](target["ip"], known or target.get("name"))
            store.put("last", {"brand": target["brand"], "ip": target["ip"], "name": known or target.get("name")})
            try:
                self.state = await self.driver.connect()
            except Offline:
                self.state = "offline"

    async def disconnect(self):
        """Drop the connection and stop auto-reconnecting until connect() is called."""
        async with self.lock:
            await self._drop()
            self.state = "disconnected"

    async def start_pairing(self):
        if not self.driver:
            await self.connect()
        if self.state != "needs_pairing":
            return
        self.error = None
        await self.driver.start_pairing()
        self.state = "pairing"
        if self.driver.pairing == "prompt":  # nothing to type; wait for the user to accept on the TV
            self.watch = asyncio.create_task(self._await_accept())

    async def _await_accept(self):
        try:
            await self.driver.finish_pairing(None)
            self.state = "ready"
        except OSError:
            self.state, self.error = "needs_pairing", "Couldn't reach the TV. Is it on and on this Wi-Fi?"
        except Exception as e:
            self.state, self.error = "needs_pairing", str(e) or "Pairing failed."

    async def finish_pairing(self, code):
        if self.state != "pairing":
            raise RuntimeError("Pairing was not started.")
        await self.driver.finish_pairing(code)
        self.state = "ready"

    async def press(self, key):
        if self.state != "ready":
            raise RuntimeError("TV not connected.")
        await self.driver.press(key)

    async def type_text(self, text):
        if self.state != "ready":
            raise RuntimeError("TV not connected.")
        await self.driver.type_text(text)


tv = Tv()


async def api(method, path, body):
    if path == "/api/status":
        return 200, tv.view()
    if path == "/api/connect" and method == "POST":
        target = {"brand": body.get("brand"), "ip": str(body.get("ip", "")).strip()} if body.get("ip") else None
        await tv.connect(target)
        return 200, tv.view()
    if path == "/api/disconnect" and method == "POST":
        await tv.disconnect()
        return 200, tv.view()
    if path == "/api/pair/start" and method == "POST":
        await tv.start_pairing()
        return 200, tv.view()
    if path == "/api/pair/finish" and method == "POST":
        try:
            await tv.finish_pairing(str(body.get("code", "")).strip())
        except Exception as e:  # wrong code, TV closed the session, ...
            tv.state = "needs_pairing"
            return 400, {**tv.view(), "error": str(e) or "Pairing failed."}
        return 200, tv.view()
    if path == "/api/key" and method == "POST":
        key = body.get("key")
        if key not in ALL_KEYS:
            return 400, {"error": "Unknown key."}
        try:
            await tv.press(key)
        except Unsupported as e:
            return 400, {"error": str(e)}
        except Exception as e:
            return 409, {**tv.view(), "error": str(e)}
        return 200, {"ok": True}
    if path == "/api/text" and method == "POST":
        text = str(body.get("text", ""))[:200]
        try:
            await tv.type_text(text)
        except Unsupported as e:
            return 400, {"error": str(e)}
        except Exception as e:
            return 409, {**tv.view(), "error": str(e)}
        return 200, {"ok": True}
    return 404, {"error": "Not found."}

TYPES = {".html": "text/html; charset=utf-8", ".css": "text/css", ".js": "text/javascript",
         ".json": "application/json", ".svg": "image/svg+xml", ".png": "image/png"}


async def handle(reader, writer):
    try:
        head = await reader.readuntil(b"\r\n\r\n")
        lines = head.decode("latin-1").split("\r\n")
        method, target, _ = lines[0].split(" ", 2)
        path = target.split("?")[0]
        headers = {k.lower(): v.strip() for k, v in (l.split(":", 1) for l in lines[1:] if ":" in l)}
        raw = await reader.readexactly(int(headers.get("content-length", 0)))

        if path.startswith("/api/"):
            try:
                body = json.loads(raw) if raw else {}
            except ValueError:
                body = {}
            status, data = await api(method, path, body)
            payload, ctype = json.dumps(data).encode(), "application/json"
        else:
            file = (WEB / ("index.html" if path == "/" else path.lstrip("/"))).resolve()
            if WEB.resolve() in file.parents and file.is_file():
                status, payload, ctype = 200, file.read_bytes(), TYPES.get(file.suffix, "application/octet-stream")
            else:
                status, payload, ctype = 404, b"Not found", "text/plain"

        writer.write(
            f"HTTP/1.1 {status} OK\r\nContent-Type: {ctype}\r\nContent-Length: {len(payload)}\r\n"
            f"Cache-Control: no-store\r\nConnection: close\r\n\r\n".encode() + payload
        )
        await writer.drain()
    except (asyncio.IncompleteReadError, ConnectionError):
        pass
    finally:
        writer.close()


def lan_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))
        return s.getsockname()[0]
    except OSError:
        return "localhost"
    finally:
        s.close()


async def main():
    server = await asyncio.start_server(handle, "0.0.0.0", PORT)
    print(f"Open on your phone: http://{lan_ip()}:{PORT}")
    asyncio.create_task(tv.connect())
    async with server:
        await server.serve_forever()


if __name__ == "__main__":
    asyncio.run(main())

