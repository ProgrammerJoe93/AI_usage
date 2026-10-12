"""Claude: reuses the OAuth login Claude Code stores and its /usage endpoint."""
import os
import time

from .common import NotConfigured, ProviderError, expand, http_json, limit, read_json, to_ms

NAME = "Claude"
USAGE_URL = "https://api.anthropic.com/api/oauth/usage"
LIMITS = [
    ("five_hour", "Current session", "5h"),
    ("seven_day", "Weekly (all models)", "7d"),
    ("seven_day_opus", "Weekly (Opus)", "op"),
    ("seven_day_sonnet", "Weekly (Sonnet)", "so"),
]


def credentials_path(override):
    if override:
        return expand(override)
    config_dir = os.environ.get("CLAUDE_CONFIG_DIR") or os.path.expanduser("~/.claude")
    return os.path.join(config_dir, ".credentials.json")


def fetch(opts):
    path = credentials_path(opts.get("claude_credentials"))
    try:
        oauth = read_json(path)["claudeAiOauth"]
        token = oauth["accessToken"]
    except FileNotFoundError:
        raise NotConfigured(f"No credentials at {path}. Log in with `claude` first.")
    except (KeyError, ValueError) as e:
        raise ProviderError(f"Could not read OAuth token from {path}: {e}")

    # Never refresh the token here: that would rotate the one Claude Code uses.
    expires_at = oauth.get("expiresAt")
    if expires_at and expires_at / 1000 < time.time():
        raise ProviderError("Login token expired. Run `claude` once to refresh it.", expired=True)

    data = http_json(USAGE_URL, headers={
        "Authorization": f"Bearer {token}",
        "anthropic-beta": "oauth-2025-04-20",
    }, auth_hint="Run `claude` to re-authenticate.")

    limits = []
    for key, label, short in LIMITS:
        entry = data.get(key)
        if not entry or entry.get("utilization") is None:
            continue
        limits.append(limit(key, label, short, entry["utilization"], to_ms(entry.get("resets_at"))))

    return {"plan": oauth.get("subscriptionType"), "limits": limits}
