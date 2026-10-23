"""Tiny JSON file for pairing tokens and the last-used TV. Kept out of git."""
import json
from pathlib import Path

FILE = Path(__file__).parent / "settings.json"


def _load():
    try:
        return json.loads(FILE.read_text())
    except (OSError, ValueError):
        return {}


def get(key, default=None):
    return _load().get(key, default)


def put(key, value):
    data = _load()
    if value is None:
        data.pop(key, None)
    else:
        data[key] = value
    FILE.write_text(json.dumps(data, indent=2))
