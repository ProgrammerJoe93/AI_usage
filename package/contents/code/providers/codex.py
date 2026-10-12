"""Codex: reuses the ChatGPT login the codex CLI stores in ~/.codex/auth.json.

Never refreshes the token: OpenAI rotates refresh tokens, so redeeming it
here would log the codex CLI out. Any `codex` run refreshes it instead.
"""
import os
import time

from .common import (NotConfigured, ProviderError, expand, http_json, jwt_claims, read_json,
                     to_ms)

NAME = "Codex"
WINDOW_NAMES = {300: ("Current session", "5h"), 10080: ("Weekly", "7d"),
                43200: ("Monthly", "mo")}
PLAN_NAMES = {"pro": "Pro 20x", "prolite": "Pro 5x"}


def codex_home():
    return expand(os.environ.get("CODEX_HOME") or "~/.codex")


def usage_url():
    base = "https://chatgpt.com/backend-api"
    try:
        with open(os.path.join(codex_home(), "config.toml")) as f:
            for line in f:
                key, _, value = line.split("#", 1)[0].partition("=")
                if key.strip() == "chatgpt_base_url" and value.strip():
                    base = value.strip().strip("\"'").rstrip("/")
    except OSError:
        pass
    if base.startswith(("https://chatgpt.com", "https://chat.openai.com")) \
            and "/backend-api" not in base:
        base += "/backend-api"
    return base + ("/wham/usage" if "/backend-api" in base else "/api/codex/usage")


def window_limit(key, window, fallback_label, fallback_short, prefix=""):
    if not window or window.get("used_percent") is None:
        return None
    minutes = (window.get("limit_window_seconds") or 0) // 60
    label, short = WINDOW_NAMES.get(minutes, (fallback_label, fallback_short))
    resets = to_ms(window.get("reset_at"))
    if resets is None and window.get("reset_after_seconds") is not None:
        resets = int((time.time() + window["reset_after_seconds"]) * 1000)
    return {"key": key, "label": prefix + label, "short": short,
            "percent": float(window["used_percent"]), "resetsAt": resets, "detail": None,
            "minutes": minutes}


def windows(rate_limit, key_prefix="", label_prefix=""):
    rate_limit = rate_limit or {}
    found = [w for w in (
        window_limit(key_prefix + "primary", rate_limit.get("primary_window"),
                     "Current session", "5h", label_prefix),
        window_limit(key_prefix + "secondary", rate_limit.get("secondary_window"),
                     "Weekly", "7d", label_prefix),
    ) if w]
    # Shorter windows first, so the panel shows session above weekly.
    found.sort(key=lambda w: w["minutes"] or float("inf"))
    for w in found:
        del w["minutes"]
    return found


def plan_name(plan):
    if not plan:
        return None
    return PLAN_NAMES.get(plan) or " ".join(p.capitalize() for p in plan.replace("-", "_").split("_"))


def fetch(opts):
    path = os.path.join(codex_home(), "auth.json")
    try:
        auth = read_json(path)
    except FileNotFoundError:
        raise NotConfigured(f"No credentials at {path}. Log in with `codex` first.")
    except ValueError as e:
        raise ProviderError(f"Could not read {path}: {e}")
    if auth.get("OPENAI_API_KEY"):
        raise NotConfigured("Codex is logged in with an API key, which has no plan limits.")

    tokens = auth.get("tokens") or {}
    token = tokens.get("access_token") or tokens.get("accessToken")
    if not token:
        raise NotConfigured(f"No ChatGPT login in {path}. Log in with `codex` first.")
    claims = jwt_claims(token)
    if claims.get("exp") and claims["exp"] < time.time():
        raise ProviderError("Login token expired. Run `codex` once to refresh it.", expired=True)

    id_claims = jwt_claims(tokens.get("id_token") or tokens.get("idToken") or "")
    openai_auth = id_claims.get("https://api.openai.com/auth") or {}
    account = (tokens.get("account_id") or tokens.get("accountId")
               or openai_auth.get("chatgpt_account_id") or id_claims.get("chatgpt_account_id"))
    headers = {"Authorization": f"Bearer {token}"}
    if account:
        headers["ChatGPT-Account-Id"] = account

    data = http_json(usage_url(), headers=headers, auth_hint="Run `codex` to log in again.")

    limits = windows(data.get("rate_limit"))
    for extra in data.get("additional_rate_limits") or []:
        name = extra.get("limit_name") or extra.get("metered_feature") or "Other"
        limits += windows(extra.get("rate_limit"), f"{name}-", f"{name} ")

    credits = data.get("credits") or {}
    if credits.get("has_credits") and not credits.get("unlimited") and limits:
        try:
            limits[0]["detail"] = f"{float(credits.get('balance')):.0f} credits left"
        except (TypeError, ValueError):
            pass

    plan = data.get("plan_type") or openai_auth.get("chatgpt_plan_type")
    return {"plan": plan_name(plan), "limits": limits}
