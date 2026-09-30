#!/usr/bin/env python3
"""Fetch Claude subscription usage using the Claude Code OAuth login.

Reads the access token Claude Code stores after `claude` login (no API key
needed) and queries the same endpoint Claude Code's /usage command uses.
Always prints a single JSON object to stdout and exits 0.
"""
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime

USAGE_URL = "https://api.anthropic.com/api/oauth/usage"

LABELS = {
    "five_hour": "Current session",
    "seven_day": "Weekly (all models)",
    "seven_day_opus": "Weekly (Opus)",
    "seven_day_sonnet": "Weekly (Sonnet)",
}


def emit(obj):
    print(json.dumps(obj))
    sys.exit(0)


def credentials_path():
    if len(sys.argv) > 1 and sys.argv[1]:
        return os.path.expanduser(sys.argv[1])
    config_dir = os.environ.get("CLAUDE_CONFIG_DIR") or os.path.expanduser("~/.claude")
    return os.path.join(config_dir, ".credentials.json")


def to_ms(iso):
    if not iso:
        return None
    try:
        return int(datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp() * 1000)
    except ValueError:
        return None


def main():
    path = credentials_path()
    try:
        with open(path) as f:
            oauth = json.load(f)["claudeAiOauth"]
        token = oauth["accessToken"]
    except FileNotFoundError:
        emit({"error": f"No credentials at {path}. Log in with `claude` first."})
    except (KeyError, ValueError) as e:
        emit({"error": f"Could not read OAuth token from {path}: {e}"})

    expires_at = oauth.get("expiresAt")
    if expires_at and expires_at / 1000 < time.time():
        emit({"error": "Login token expired. Run `claude` once to refresh it.", "expired": True})

    req = urllib.request.Request(USAGE_URL, headers={
        "Authorization": f"Bearer {token}",
        "anthropic-beta": "oauth-2025-04-20",
        "Accept": "application/json",
        "User-Agent": "claude-usage-plasmoid/1.0",
    })
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.load(resp)
    except urllib.error.HTTPError as e:
        if e.code == 401:
            emit({"error": "Token rejected (401). Run `claude` to re-authenticate.", "expired": True})
        emit({"error": f"HTTP {e.code} from usage endpoint"})
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        emit({"error": f"Network error: {getattr(e, 'reason', e)}"})
    except ValueError:
        emit({"error": "Invalid JSON from usage endpoint"})

    limits = []
    for key, label in LABELS.items():
        entry = data.get(key)
        if not entry or entry.get("utilization") is None:
            continue
        limits.append({
            "key": key,
            "label": label,
            "percent": float(entry["utilization"]),
            "resetsAt": to_ms(entry.get("resets_at")),
        })

    emit({
        "plan": oauth.get("subscriptionType"),
        "limits": limits,
        "fetchedAt": int(time.time() * 1000),
    })


if __name__ == "__main__":
    main()
