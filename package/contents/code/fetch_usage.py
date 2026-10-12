#!/usr/bin/env python3
"""Fetch AI subscription usage for Claude, Codex, Copilot, Antigravity and OpenCode.

Each provider reuses the login the tool itself saved locally (no API keys
to configure) and queries the same usage endpoint the tool uses. Tokens are
never refreshed here, so the tools' own logins are left alone.

Always prints a single JSON object to stdout and exits 0:
  {"providers": [{"id", "name", "plan", "limits": [...], "error", "expired"}],
   "fetchedAt": ms}
Providers that aren't installed or logged in are left out.
"""
import argparse
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from providers import antigravity, claude, codex, copilot, opencode  # noqa: E402
from providers.common import NotConfigured, ProviderError, now_ms  # noqa: E402

PROVIDERS = {
    "claude": claude,
    "codex": codex,
    "copilot": copilot,
    "antigravity": antigravity,
    "opencode": opencode,
}


def run(pid, opts):
    module = PROVIDERS[pid]
    result = {"id": pid, "name": module.NAME, "plan": None, "limits": [],
              "error": None, "expired": False}
    try:
        result.update(module.fetch(opts))
    except NotConfigured as e:
        if not opts["explicit"]:
            return None
        result["error"] = str(e)
    except ProviderError as e:
        result["error"] = str(e)
        result["expired"] = e.expired
    except Exception as e:  # keep one broken provider from hiding the others
        result["error"] = f"{type(e).__name__}: {e}"
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--providers", default=",".join(PROVIDERS),
                        help="comma-separated provider ids")
    parser.add_argument("--explicit", action="store_true",
                        help="report providers that aren't set up instead of hiding them")
    parser.add_argument("--claude-credentials", default="")
    args = parser.parse_args()

    opts = {
        "explicit": args.explicit,
        "claude_credentials": args.claude_credentials,
    }
    ids = [p for p in (s.strip() for s in args.providers.split(",")) if p in PROVIDERS]
    with ThreadPoolExecutor(max_workers=max(1, len(ids))) as pool:
        results = list(pool.map(lambda pid: run(pid, opts), ids))

    print(json.dumps({"providers": [r for r in results if r], "fetchedAt": now_ms()}))


if __name__ == "__main__":
    main()
