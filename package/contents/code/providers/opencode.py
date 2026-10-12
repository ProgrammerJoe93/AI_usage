"""OpenCode Go: the Go usage API, or a local estimate from opencode's database.

The API needs an opencode API key: OPENCODE_API_KEY, or the key `opencode
auth login` saved for the "opencode-go" (or "opencode" Zen) provider.
Without a key, spending is summed from opencode's local message history and
compared against the default Go limits, which is only an estimate.
"""
import json
import os
import sqlite3
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

from .common import (USER_AGENT, NotConfigured, ProviderError, now_ms, read_json, to_ms,
                     xdg)

NAME = "OpenCode Go"
USAGE_URL = "https://opencode.ai/zen/go/v1/usage"
WINDOWS = [
    ("rolling", "5-hour window", "5h"),
    ("weekly", "Weekly", "7d"),
    ("monthly", "Monthly", "mo"),
]
# Dollar limits of the default Go model; used only for the local estimate.
ESTIMATE_LIMITS = {"rolling": 12.0, "weekly": 30.0, "monthly": 60.0}


def data_dir():
    return os.path.join(xdg("XDG_DATA_HOME", "~/.local/share"), "opencode")


def find_key():
    if os.environ.get("OPENCODE_API_KEY"):
        return os.environ["OPENCODE_API_KEY"]
    try:
        content = os.environ.get("OPENCODE_AUTH_CONTENT")
        auth = json.loads(content) if content else read_json(os.path.join(data_dir(), "auth.json"))
    except (OSError, ValueError):
        return None
    for provider in ("opencode-go", "opencode"):
        entry = auth.get(provider) or {}
        if entry.get("type") == "api" and entry.get("key"):
            return entry["key"]
    return None


def fetch_api(key):
    req = urllib.request.Request(USAGE_URL, headers={
        "Authorization": f"Bearer {key}",
        "Accept": "application/json",
        "User-Agent": USER_AGENT,
    })
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.load(resp)
    except urllib.error.HTTPError as e:
        try:
            message = json.load(e).get("error", {}).get("message")
        except (ValueError, AttributeError):
            message = None
        if e.code == 401:
            raise ProviderError("OpenCode API key rejected. Check the key or run "
                                "`opencode auth login`.", expired=True)
        if e.code == 403:
            raise NotConfigured(message or "No OpenCode Go subscription.")
        raise ProviderError(message or f"HTTP {e.code} from OpenCode usage endpoint")
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise ProviderError(f"Network error: {getattr(e, 'reason', e)}")
    except ValueError:
        raise ProviderError("Invalid JSON from OpenCode usage endpoint")

    usage = data.get("usage") or {}
    limits = []
    for key_, label, short in WINDOWS:
        window = usage.get(key_)
        if not window:
            continue
        percent = window.get("percent", window.get("usagePercent"))
        if percent is None:
            continue
        resets = to_ms(window.get("resetsAt"))
        if resets is None and window.get("resetInSec") is not None:
            resets = now_ms() + int(window["resetInSec"] * 1000)
        limits.append({"key": key_, "label": label, "short": short,
                       "percent": float(percent), "resetsAt": resets, "detail": None})
    if not limits:
        raise ProviderError("Unexpected response from OpenCode usage endpoint")
    return {"plan": "Go", "limits": limits}


# Step-finish parts carry per-step cost; fall back to the message cost when a
# message has none, so nothing is counted twice.
COST_QUERY = """
WITH m AS (
  SELECT id,
    CAST(COALESCE(json_extract(data, '$.time.created'), time_created) AS INTEGER) AS t,
    json_extract(data, '$.cost') AS cost
  FROM message
  WHERE json_valid(data)
    AND json_extract(data, '$.providerID') = 'opencode-go'
    AND json_extract(data, '$.role') = 'assistant'
    AND CAST(COALESCE(json_extract(data, '$.time.created'), time_created) AS INTEGER) >= ?)
SELECT CAST(COALESCE(json_extract(p.data, '$.time.created'), p.time_created, m.t) AS INTEGER),
       CAST(json_extract(p.data, '$.cost') AS REAL)
FROM part p JOIN m ON m.id = p.message_id
WHERE json_valid(p.data) AND json_extract(p.data, '$.type') = 'step-finish'
  AND json_type(p.data, '$.cost') IN ('integer', 'real')
UNION ALL
SELECT t, CAST(cost AS REAL) FROM m
WHERE cost IS NOT NULL AND NOT EXISTS (
  SELECT 1 FROM part p WHERE p.message_id = m.id AND json_valid(p.data)
    AND json_extract(p.data, '$.type') = 'step-finish'
    AND json_type(p.data, '$.cost') IN ('integer', 'real'))
"""


def estimate_local():
    path = os.environ.get("OPENCODE_DB") or os.path.join(data_dir(), "opencode.db")
    if not os.path.exists(path):
        raise NotConfigured("OpenCode is not installed.")

    now = datetime.now(timezone.utc)
    week_start = (now - timedelta(days=now.weekday())).replace(
        hour=0, minute=0, second=0, microsecond=0)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    next_month = (month_start + timedelta(days=32)).replace(day=1)
    since = min(week_start, month_start, now - timedelta(hours=5))
    try:
        db = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=0.25)
        try:
            rows = db.execute(COST_QUERY, (int(since.timestamp() * 1000),)).fetchall()
        finally:
            db.close()
    except sqlite3.Error as e:
        if "no such table" in str(e):
            raise NotConfigured("No OpenCode usage history.")
        raise ProviderError(f"Could not read {path}: {e}")

    rows = [(t, c) for t, c in rows if t and t > 0 and c is not None and c >= 0]
    if not rows:
        raise NotConfigured("No OpenCode Go usage found and no API key.")

    now_t = now.timestamp() * 1000
    rolling_start = now_t - 5 * 3600 * 1000
    rolling = [(t, c) for t, c in rows if t >= rolling_start]
    windows = {
        "rolling": (sum(c for _, c in rolling),
                    int(min(t for t, _ in rolling) + 5 * 3600 * 1000) if rolling else None),
        "weekly": (sum(c for t, c in rows if t >= week_start.timestamp() * 1000),
                   int((week_start + timedelta(days=7)).timestamp() * 1000)),
        "monthly": (sum(c for t, c in rows if t >= month_start.timestamp() * 1000),
                    int(next_month.timestamp() * 1000)),
    }
    limits = []
    for key, label, short in WINDOWS:
        used, resets = windows[key]
        cap = ESTIMATE_LIMITS[key]
        limits.append({"key": key, "label": label + " (estimate)", "short": short,
                       "percent": min(100.0, used / cap * 100), "resetsAt": resets,
                       "detail": f"${used:.2f} of ~${cap:.0f} on this computer"})
    return {"plan": "Go (estimated)", "limits": limits}


def fetch(opts):
    key = find_key()
    if key:
        return fetch_api(key)
    return estimate_local()
