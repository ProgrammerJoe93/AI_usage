"""Shared helpers for the usage providers."""
import base64
import json
import os
import ssl
import time
import urllib.error
import urllib.request
from datetime import datetime

USER_AGENT = "ai-usage-plasmoid/2.0"


class NotConfigured(Exception):
    """The tool isn't installed or logged in; the provider is hidden."""


class ProviderError(Exception):
    def __init__(self, message, expired=False):
        super().__init__(message)
        self.expired = expired


def expand(path):
    return os.path.expanduser(os.path.expandvars(path))


def xdg(var, default):
    return os.environ.get(var) or os.path.expanduser(default)


def read_json(path):
    with open(path) as f:
        return json.load(f)


def to_ms(value):
    """ISO-8601 string, unix seconds or unix ms -> unix ms."""
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)):
        return int(value if value > 1e12 else value * 1000)
    try:
        return int(datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp() * 1000)
    except ValueError:
        return None


def now_ms():
    return int(time.time() * 1000)


def jwt_claims(token):
    try:
        payload = token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        return json.loads(base64.urlsafe_b64decode(payload))
    except (IndexError, ValueError):
        return {}


def http_json(url, headers=None, body=None, method=None, insecure=False, timeout=15,
              name="usage endpoint", auth_hint=""):
    """Request JSON. Raises ProviderError with a readable message on failure."""
    data = None
    headers = {"Accept": "application/json", "User-Agent": USER_AGENT, **(headers or {})}
    if body is not None:
        data = json.dumps(body).encode()
        headers.setdefault("Content-Type", "application/json")
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    context = None
    if insecure:
        context = ssl.create_default_context()
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=context) as resp:
            return json.load(resp)
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            raise ProviderError(f"Token rejected ({e.code}). {auth_hint}".strip(), expired=True)
        raise ProviderError(f"HTTP {e.code} from {name}")
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise ProviderError(f"Network error: {getattr(e, 'reason', e)}")
    except ValueError:
        raise ProviderError(f"Invalid JSON from {name}")


def limit(key, label, short, percent, resets_at=None, detail=None):
    return {
        "key": key,
        "label": label,
        "short": short,
        "percent": max(0.0, float(percent)),
        "resetsAt": resets_at,
        "detail": detail,
    }
