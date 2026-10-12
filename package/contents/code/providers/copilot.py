"""GitHub Copilot: premium request and chat quotas from copilot_internal/user.

Uses the GitHub OAuth token of the Copilot CLI, the editor plugins
(VS Code/neovim) or the gh CLI, whichever is found first.
"""
import json
import os
import shutil
import subprocess
from datetime import datetime, timedelta, timezone

from .common import NotConfigured, ProviderError, expand, http_json, read_json, to_ms, xdg

NAME = "GitHub Copilot"
USER_URL = "https://api.github.com/copilot_internal/user"
QUOTAS = [
    ("premium_interactions", "Premium requests", "pr"),
    ("chat", "Chat", "ch"),
    ("completions", "Code completions", "cc"),
]


def usable(token):
    # Copilot refuses classic personal access tokens.
    return token if token and not token.startswith("ghp_") else None


def run(cmd):
    if not shutil.which(cmd[0]):
        return None
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return out.stdout.strip() if out.returncode == 0 else None


def copilot_cli_tokens():
    home = expand(os.environ.get("COPILOT_HOME") or "~/.copilot")
    try:
        with open(os.path.join(home, "config.json")) as f:
            # The file starts with // comment lines.
            config = json.loads("".join(l for l in f if not l.lstrip().startswith("//")))
    except (OSError, ValueError):
        return
    user = config.get("lastLoggedInUser") or config.get("last_logged_in_user") or {}
    account = f"{user.get('host', 'https://github.com')}:{user.get('login')}" \
        if user.get("login") else None
    stored = config.get("copilotTokens") or config.get("copilot_tokens") or {}
    if account and stored.get(account):
        yield stored[account]
    yield from stored.values()
    if account:
        # Default storage: the system keyring (KWallet / GNOME Keyring).
        yield run(["secret-tool", "lookup", "service", "copilot-cli", "account", account])


def editor_tokens():
    folder = os.path.join(xdg("XDG_CONFIG_HOME", "~/.config"), "github-copilot")
    for name in ("apps.json", "hosts.json"):
        try:
            data = read_json(os.path.join(folder, name))
        except (OSError, ValueError):
            continue
        for host, entry in data.items():
            if host.split(":")[0] == "github.com" and isinstance(entry, dict):
                yield entry.get("oauth_token") or entry.get("access_token")


def candidate_tokens():
    for var in ("COPILOT_GITHUB_TOKEN", "GH_TOKEN", "GITHUB_TOKEN"):
        yield os.environ.get(var)
    yield from copilot_cli_tokens()
    yield from editor_tokens()
    yield run(["gh", "auth", "token", "--hostname", "github.com"])


def quota_limit(key, label, short, snap, resets):
    if not snap or snap.get("unlimited"):
        return None
    try:
        entitlement = float(snap.get("entitlement") or 0)
        remaining = float(snap.get("remaining") or 0)
    except (TypeError, ValueError):
        return None
    if entitlement == -1 or (entitlement == 0 and remaining == 0):
        return None  # unlimited, or a placeholder on token-billed seats
    pct_left = snap.get("percent_remaining")
    if pct_left is None:
        if entitlement <= 0:
            return None
        pct_left = remaining / entitlement * 100
    used = max(0.0, entitlement - remaining)
    return {"key": key, "label": label, "short": short,
            "percent": max(0.0, 100 - float(pct_left)), "resetsAt": resets,
            "detail": f"{used:.0f} of {entitlement:.0f} used" if entitlement > 0 else None}


def reset_ms(value):
    """quota_reset_date is often a bare date; it resets at midnight UTC."""
    if not value:
        return None
    if len(str(value)) == 10:
        try:
            day = datetime.strptime(value, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            return int(day.timestamp() * 1000)
        except ValueError:
            return None
    return to_ms(value)


def fetch(opts):
    tried = set()
    last_error = None
    for token in filter(usable, candidate_tokens()):
        if token in tried:
            continue
        tried.add(token)
        try:
            data = http_json(USER_URL, headers={
                "Authorization": f"token {token}",
                "Editor-Version": "vscode/1.96.2",
                "Editor-Plugin-Version": "copilot-chat/0.26.7",
                "X-Github-Api-Version": "2025-04-01",
            }, auth_hint="Log in again with `copilot` or `gh auth login`.")
        except ProviderError as e:
            # A stale token from one source shouldn't hide a working one elsewhere.
            last_error = e
            if e.expired:
                continue
            raise
        return parse(data)
    if last_error:
        raise last_error
    raise NotConfigured("No GitHub login found for Copilot.")


def parse(data):
    resets = reset_ms(data.get("quota_reset_date_utc") or data.get("quota_reset_date"))
    snapshots = data.get("quota_snapshots") or {}
    limits = [l for l in (quota_limit(k, label, short, snapshots.get(k), resets)
                          for k, label, short in QUOTAS) if l]

    # Free plan: monthly totals and remaining counts come as separate maps.
    monthly = data.get("monthly_quotas") or {}
    left = data.get("limited_user_quotas") or {}
    free_reset = reset_ms(data.get("limited_user_reset_date")) or resets
    have = {l["key"] for l in limits}
    for key, label, short in QUOTAS:
        if key in have or not monthly.get(key):
            continue
        total = float(monthly[key])
        remaining = float(left.get(key, total))
        limits.append({"key": key, "label": label, "short": short,
                       "percent": max(0.0, min(100.0, 100 - remaining / total * 100)),
                       "resetsAt": free_reset,
                       "detail": f"{total - remaining:.0f} of {total:.0f} used"})

    plan = data.get("copilot_plan") or data.get("access_type_sku")
    if plan:
        plan = plan.replace("_", " ").title()
    return {"plan": plan, "limits": limits}
