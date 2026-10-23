"""Pair with a discovered Android TV and send a key press."""
import asyncio
import sys
from androidtvremote2 import AndroidTVRemote, CannotConnect, InvalidAuth
from discover import discover


async def main(key):
    tvs = await discover()
    if not tvs:
        sys.exit("No TV found on this network.")
    name, ip, _ = tvs[0]
    print(f"Using {name} at {ip}")

    remote = AndroidTVRemote("tv-controller", "cert.pem", "key.pem", ip)
    if await remote.async_generate_cert_if_missing():
        print("Made a new certificate.")
    try:
        await remote.async_connect()
    except InvalidAuth:
        # First time: the TV shows a code on screen.
        await remote.async_start_pairing()
        code = input("Type the code shown on the TV: ")
        await remote.async_finish_pairing(code)
        await remote.async_connect()
    except CannotConnect:
        sys.exit("The TV did not answer.")

    remote.send_key_command(key)
    await asyncio.sleep(1)
    remote.disconnect()


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else "VOLUME_UP"))
