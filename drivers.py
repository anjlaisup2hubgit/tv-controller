"""One driver per TV brand. Each turns the page's generic button names into that brand's protocol.

A driver's `pairing` is None (no pairing), "code" (TV shows a code to type in) or
"prompt" (TV shows an Allow/Accept box; nothing to type).
Buttons missing from a driver's KEYS are reported as "not supported on this TV".
"""
import asyncio
import re
import urllib.parse
import urllib.request

import store


class Offline(Exception):
    """The TV did not answer."""


class Unsupported(Exception):
    """This brand has no equivalent for the pressed button."""


class Driver:
    brand = ""
    label = ""
    pairing = None
    KEYS = {}

    def __init__(self, ip, name=None):
        self.ip = ip
        self.name = name or f"{self.label} {ip}"

    def native(self, key):
        if key not in self.KEYS:
            raise Unsupported(f"{key.replace('_', ' ').title()} isn't available on {self.label} TVs.")
        return self.KEYS[key]

    async def connect(self):
        """Return "ready" or "needs_pairing"; raise Offline if the TV can't be reached."""
        raise NotImplementedError

    async def start_pairing(self):
        pass

    async def finish_pairing(self, code):
        pass

    async def press(self, key):
        raise NotImplementedError

    async def type_text(self, text):
        raise Unsupported(f"Typing isn't available on {self.label} TVs.")

    async def close(self):
        pass


# ---------------------------------------------------------------- Android TV / Google TV
# Sony, Philips, TCL, Hisense, Xiaomi, Nvidia Shield and anything running Android TV.
class AndroidTv(Driver):
    brand, label, pairing = "android", "Android TV", "code"
    KEYS = {
        "POWER": "POWER", "VOL_UP": "VOLUME_UP", "VOL_DOWN": "VOLUME_DOWN",
        "MUTE": "VOLUME_MUTE", "HOME": "HOME", "MENU": "MENU",
        "SOURCE": "TV_INPUT", "CH_UP": "CHANNEL_UP", "CH_DOWN": "CHANNEL_DOWN",
        "TV": "TV", "EXIT": "ESCAPE", "INFO": "INFO", "OPTIONS": "TV_CONTENTS_MENU",
        "BACK": "BACK", "GUIDE": "GUIDE", "SEARCH": "SEARCH",
        "ASPECT": "TV_ZOOM_MODE", "SETTINGS": "SETTINGS",
        "UP": "DPAD_UP", "DOWN": "DPAD_DOWN", "LEFT": "DPAD_LEFT",
        "RIGHT": "DPAD_RIGHT", "OK": "DPAD_CENTER",
        "RED": "PROG_RED", "GREEN": "PROG_GREEN", "YELLOW": "PROG_YELLOW",
        "BLUE": "PROG_BLUE",
        "PLAY_PAUSE": "MEDIA_PLAY_PAUSE", "STOP": "MEDIA_STOP",
        "REWIND": "MEDIA_REWIND", "FORWARD": "MEDIA_FAST_FORWARD",
        "PREV": "MEDIA_PREVIOUS", "NEXT": "MEDIA_NEXT",
        "LAST": "LAST_CHANNEL", "DEL": "DEL", "ENTER": "ENTER",
        **{str(n): str(n) for n in range(10)},
    }

    def __init__(self, ip, name=None):
        super().__init__(ip, name)
        from androidtvremote2 import AndroidTVRemote
        self.remote = AndroidTVRemote("tv-controller", "cert.pem", "key.pem", ip)
        self.typed = ""  # what we've put in the TV's focused text field
        self.field = None  # ime_field_counter that `typed` belongs to

    async def connect(self):
        from androidtvremote2 import CannotConnect, InvalidAuth
        await self.remote.async_generate_cert_if_missing()
        try:
            await self.remote.async_connect()
        except InvalidAuth:
            return "needs_pairing"
        except (CannotConnect, OSError, asyncio.TimeoutError):
            raise Offline()
        self.remote.keep_reconnecting()
        return "ready"

    async def start_pairing(self):
        await self.remote.async_start_pairing()

    async def finish_pairing(self, code):
        await self.remote.async_finish_pairing(code)
        await self.remote.async_connect()
        self.remote.keep_reconnecting()

    async def press(self, key):
        native = self.native(key)
        if key == "DEL":
            self.typed = self.typed[:-1]
        elif key in ("ENTER", "OK"):
            self.typed = ""
        self.remote.send_key_command(native)

    async def type_text(self, text):
        # send_text() sets the TV field's whole content (it doesn't append), and the page sends one
        # keystroke at a time, so resend everything typed since the field was focused.
        proto = getattr(self.remote, "_remote_message_protocol", None)
        if proto is None:
            raise RuntimeError("TV connection isn't ready yet.")
        field = proto.ime_field_counter
        if field != self.field:
            self.field, self.typed = field, ""
        self.typed += text
        self.remote.send_text(self.typed)

    async def close(self):
        self.remote.disconnect()


# ---------------------------------------------------------------- Roku (incl. TCL/Hisense/Sharp Roku TVs)
class Roku(Driver):
    brand, label = "roku", "Roku"
    # Roku's External Control API: plain HTTP on port 8060, no pairing.
    # On newer Roku OS: Settings > System > Advanced system settings > Control by mobile apps > Network access: Permissive.
    KEYS = {
        "POWER": "Power", "VOL_UP": "VolumeUp", "VOL_DOWN": "VolumeDown", "MUTE": "VolumeMute",
        "HOME": "Home", "INFO": "Info", "OPTIONS": "Info", "SEARCH": "Search",
        "TV": "InputTuner", "CH_UP": "ChannelUp", "CH_DOWN": "ChannelDown",
        "BACK": "Back", "UP": "Up", "DOWN": "Down", "LEFT": "Left", "RIGHT": "Right", "OK": "Select",
        "PLAY_PAUSE": "Play", "REWIND": "Rev", "FORWARD": "Fwd", "PREV": "InstantReplay",
        "DEL": "Backspace", "ENTER": "Enter",
        **{str(n): f"Lit_{n}" for n in range(10)},
    }

    def _http(self, method, path, timeout=3):
        req = urllib.request.Request(f"http://{self.ip}:8060{path}", method=method,
                                     data=b"" if method == "POST" else None)
        with urllib.request.urlopen(req, timeout=timeout) as res:
            return res.read().decode("utf-8", "replace")

    async def connect(self):
        try:
            info = await asyncio.to_thread(self._http, "GET", "/query/device-info")
        except (OSError, ValueError):
            raise Offline()
        m = re.search(r"<user-device-name>(.*?)</user-device-name>", info) \
            or re.search(r"<friendly-device-name>(.*?)</friendly-device-name>", info)
        if m and m.group(1).strip():
            self.name = m.group(1).strip()
        return "ready"

    async def press(self, key):
        try:
            await asyncio.to_thread(self._http, "POST", f"/keypress/{self.native(key)}")
        except OSError as e:
            raise RuntimeError(f"Roku didn't answer ({e}).")

    async def type_text(self, text):
        # One Lit_<char> keypress per character.
        try:
            for ch in text:
                await asyncio.to_thread(self._http, "POST", f"/keypress/Lit_{urllib.parse.quote(ch, safe='')}")
        except OSError as e:
            raise RuntimeError(f"Roku didn't answer ({e}).")


# ---------------------------------------------------------------- Samsung Tizen (2016+)
class Samsung(Driver):
    brand, label, pairing = "samsung", "Samsung", "prompt"
    KEYS = {
        "POWER": "KEY_POWER", "VOL_UP": "KEY_VOLUP", "VOL_DOWN": "KEY_VOLDOWN", "MUTE": "KEY_MUTE",
        "HOME": "KEY_HOME", "MENU": "KEY_MENU", "SOURCE": "KEY_SOURCE", "TV": "KEY_TV",
        "CH_UP": "KEY_CHUP", "CH_DOWN": "KEY_CHDOWN", "EXIT": "KEY_EXIT", "INFO": "KEY_INFO",
        "OPTIONS": "KEY_TOOLS", "BACK": "KEY_RETURN", "GUIDE": "KEY_GUIDE", "ASPECT": "KEY_PICTURE_SIZE",
        "UP": "KEY_UP", "DOWN": "KEY_DOWN", "LEFT": "KEY_LEFT", "RIGHT": "KEY_RIGHT", "OK": "KEY_ENTER",
        "RED": "KEY_RED", "GREEN": "KEY_GREEN", "YELLOW": "KEY_YELLOW", "BLUE": "KEY_BLUE",
        "STOP": "KEY_STOP", "REWIND": "KEY_REWIND", "FORWARD": "KEY_FF", "LAST": "KEY_PRECH",
        "PLAY_PAUSE": None,  # handled in press()
        **{str(n): f"KEY_{n}" for n in range(10)},
    }

    def __init__(self, ip, name=None):
        super().__init__(ip, name)
        self.remote = None
        self.task = None
        self.playing = False

    def _make(self, timeout):
        from samsungtvws.async_remote import SamsungTVWSAsyncRemote
        return SamsungTVWSAsyncRemote(self.ip, port=8002, token=store.get(f"samsung:{self.ip}"),
                                      timeout=timeout, key_press_delay=0, name="TV Controller")

    async def _open(self, timeout):
        self.remote = self._make(timeout)
        await self.remote.open()
        if self.remote.token:
            store.put(f"samsung:{self.ip}", self.remote.token)

    async def connect(self):
        from samsungtvws.exceptions import ConnectionFailure
        if not store.get(f"samsung:{self.ip}"):
            return "needs_pairing"
        try:
            await self._open(5)
        except ConnectionFailure:  # token no longer accepted (TV forgot this device)
            store.put(f"samsung:{self.ip}", None)
            return "needs_pairing"
        except (OSError, asyncio.TimeoutError):
            raise Offline()
        return "ready"

    async def start_pairing(self):
        # The TV shows "Allow this device?"; open() blocks until the user answers.
        self.task = asyncio.create_task(self._open(60))

    async def finish_pairing(self, code):
        try:
            await self.task
        except Exception as e:
            raise RuntimeError("The TV didn't accept the request." if not str(e) else str(e))

    async def _send(self, native):
        from samsungtvws.remote import SendRemoteKey
        await self.remote.send_command(SendRemoteKey.click(native), key_press_delay=0)

    async def press(self, key):
        # Samsung has separate PLAY and PAUSE keys, so alternate to behave like a toggle.
        if key == "PLAY_PAUSE":
            self.playing = not self.playing
            native = "KEY_PLAY" if self.playing else "KEY_PAUSE"
        else:
            native = self.native(key)
        try:
            await self._send(native)
        except Exception:  # idle websocket was dropped by the TV; reconnect once
            await self.close()
            await self._open(5)
            await self._send(native)

    async def close(self):
        if self.task and not self.task.done():
            self.task.cancel()
        if self.remote:
            try:
                await self.remote.close()
            except Exception:
                pass
            self.remote = None


# ---------------------------------------------------------------- LG webOS
class Lg(Driver):
    brand, label, pairing = "lg", "LG", "prompt"
    KEYS = {
        "POWER": "POWER", "VOL_UP": "VOLUMEUP", "VOL_DOWN": "VOLUMEDOWN", "MUTE": "MUTE",
        "HOME": "HOME", "MENU": "MENU", "SOURCE": "INPUT_HUB", "TV": "DASH",
        "CH_UP": "CHANNELUP", "CH_DOWN": "CHANNELDOWN", "EXIT": "EXIT", "INFO": "INFO",
        "OPTIONS": "QMENU", "BACK": "BACK", "GUIDE": "GUIDE", "ASPECT": "ASPECT_RATIO",
        "UP": "UP", "DOWN": "DOWN", "LEFT": "LEFT", "RIGHT": "RIGHT", "OK": "ENTER",
        "RED": "RED", "GREEN": "GREEN", "YELLOW": "YELLOW", "BLUE": "BLUE",
        "STOP": "STOP", "REWIND": "REWIND", "FORWARD": "FASTFORWARD",
        "PLAY_PAUSE": None,  # handled in press()
        **{str(n): str(n) for n in range(10)},
    }

    def __init__(self, ip, name=None):
        super().__init__(ip, name)
        self.client = None
        self.task = None
        self.playing = False

    def _make(self, timeout):
        from aiowebostv import WebOsClient
        return WebOsClient(self.ip, client_key=store.get(f"lg:{self.ip}"), connect_timeout=timeout)

    async def _open(self, timeout):
        self.client = self._make(timeout)
        await self.client.connect()
        if self.client.client_key:
            store.put(f"lg:{self.ip}", self.client.client_key)

    async def connect(self):
        if not store.get(f"lg:{self.ip}"):
            return "needs_pairing"
        try:
            await self._open(5)
        except (OSError, asyncio.TimeoutError):
            raise Offline()
        return "ready"

    async def start_pairing(self):
        # The TV shows "Allow connection?"; connect() waits for the answer.
        self.task = asyncio.create_task(self._open(60))

    async def finish_pairing(self, code):
        try:
            await self.task
        except Exception as e:
            raise RuntimeError(str(e) or "The TV didn't accept the request.")

    async def press(self, key):
        if key == "PLAY_PAUSE":
            self.playing = not self.playing
            native = "PLAY" if self.playing else "PAUSE"
        else:
            native = self.native(key)
        try:
            await self.client.button(native)
        except Exception:
            await self.close()
            await self._open(5)
            await self.client.button(native)

    async def close(self):
        if self.task and not self.task.done():
            self.task.cancel()
        if self.client:
            try:
                await self.client.disconnect()
            except Exception:
                pass
            self.client = None


DRIVERS = {d.brand: d for d in (AndroidTv, Roku, Samsung, Lg)}
