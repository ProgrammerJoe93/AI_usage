"""Antigravity: asks the running Antigravity language server for its quota.

The desktop app, IDE and `agy` CLI each run a local language server that
serves the quota summary over HTTPS on 127.0.0.1, guarded by a CSRF token
passed on its command line. When none is running, the `agy` CLI's saved
token is used against Google's Cloud Code API, as long as it hasn't expired.
"""
import glob
import os
import re

from .common import (NotConfigured, ProviderError, expand, http_json, now_ms, read_json,
                     to_ms, xdg)

NAME = "Antigravity"
SERVICE = "/exa.language_server_pb.LanguageServerService/"
CLOUD_URL = "https://cloudcode-pa.googleapis.com/v1internal:"
METADATA = {"metadata": {"ideName": "antigravity", "extensionName": "antigravity",
                         "ideVersion": "unknown", "locale": "en"}}
LS_RE = re.compile(r"(^|[/\\])language[_-]server([_-][a-z0-9]+)*(\.exe)?(\s|$)")


def flag(cmdline, name):
    m = re.search(rf"--{name}[=\s]+(\S+)", cmdline, re.IGNORECASE)
    return m.group(1) if m else None


def find_servers():
    """Yield (pid, cmdline) for Antigravity language servers owned by us."""
    uid = os.getuid()
    for proc in glob.glob("/proc/[0-9]*"):
        try:
            if os.stat(proc).st_uid != uid:
                continue
            with open(f"{proc}/cmdline", "rb") as f:
                cmdline = f.read().replace(b"\0", b" ").decode(errors="replace").strip()
        except OSError:
            continue
        lower = cmdline.lower()
        if LS_RE.search(lower) and ("antigravity" in lower):
            yield int(proc.rsplit("/", 1)[1]), cmdline


def listening_ports(pid):
    inodes = set()
    for fd in glob.glob(f"/proc/{pid}/fd/*"):
        try:
            target = os.readlink(fd)
        except OSError:
            continue
        if target.startswith("socket:["):
            inodes.add(target[8:-1])
    ports = []
    for table in ("tcp", "tcp6"):
        try:
            with open(f"/proc/{pid}/net/{table}") as f:
                next(f)
                for line in f:
                    cols = line.split()
                    if cols[3] == "0A" and cols[9] in inodes:
                        ports.append(int(cols[1].rsplit(":", 1)[1], 16))
        except (OSError, StopIteration, IndexError, ValueError):
            continue
    return sorted(set(ports))


def call_local(port, csrf, method, body, scheme="https"):
    return http_json(f"{scheme}://127.0.0.1:{port}{SERVICE}{method}", headers={
        "Connect-Protocol-Version": "1",
        "X-Codeium-Csrf-Token": csrf,
    }, body=body, insecure=True, timeout=5, name="Antigravity language server")


def remaining_fraction(bucket):
    if bucket.get("remainingFraction") is not None:
        return bucket["remainingFraction"]
    remaining = bucket.get("remaining") or {}
    if remaining.get("remainingFraction") is not None:
        return remaining["remainingFraction"]
    if remaining.get("case") == "remainingFraction":
        return remaining.get("value")
    # Proto3 JSON drops zero values: a bucket with a reset but no fraction is used up.
    return 0.0 if bucket.get("resetTime") else None


def group_title(name):
    lower = name.lower()
    if "gemini" in lower:
        return "Gemini", 0
    if "claude" in lower or "gpt" in lower:
        return "Claude/GPT", 1
    return name, 2


def bucket_kind(bucket):
    candidates = [bucket.get("window"), bucket.get("bucketId") or bucket.get("id"),
                  bucket.get("displayName")]
    for c in filter(None, candidates):
        c = re.sub(r" limit$", "", c.lower().replace("_", "-"))
        if any(c == k or c.endswith("-" + k) or c.endswith(" " + k)
               for k in ("session", "5h", "5-hour", "five hour", "five-hour")):
            return "5-hour", "5h", 0
        if c == "weekly" or c.endswith("weekly"):
            return "weekly", "7d", 1
    return bucket.get("displayName") or bucket.get("bucketId") or "limit", "", 2


def parse_summary(data):
    payload = data.get("response") or data.get("summary") or data
    rows = []
    for group in payload.get("groups") or []:
        title, gorder = group_title(group.get("displayName") or group.get("name") or "")
        for bucket in group.get("buckets") or []:
            if bucket.get("disabled"):
                continue
            fraction = remaining_fraction(bucket)
            if fraction is None:
                continue
            kind, short, korder = bucket_kind(bucket)
            tag = "g" if gorder == 0 else "c" if gorder == 1 else ""
            rows.append(((korder, gorder), {
                "key": bucket.get("bucketId") or bucket.get("id") or f"{title}-{kind}",
                "label": f"{title} {kind}",
                "short": (tag + short) if tag and short else short or title[:2].lower(),
                "percent": 100 - max(0.0, min(1.0, float(fraction))) * 100,
                "resetsAt": to_ms(bucket.get("resetTime")),
                "detail": None,
            }))
    # 5-hour limits first so the panel shows them, then weekly.
    return [row for _, row in sorted(rows, key=lambda r: r[0])]


def model_family(model_id, label):
    text = f"{model_id} {label}".lower()
    if any(x in text for x in ("lite", "image", "autocomplete")) or model_id.startswith("tab_"):
        return None
    if "claude" in text or "gpt" in text or "openai" in text:
        return "Claude/GPT"
    if "gemini" in text:
        return "Gemini"
    return None


def parse_models(configs):
    """Older servers only report per-model quota; show the tightest model per pool."""
    pools = {}
    for cfg in configs:
        quota = cfg.get("quotaInfo")
        if not quota:
            continue
        model_id = (cfg.get("modelOrAlias") or {}).get("model") or cfg.get("model") or ""
        family = model_family(model_id, cfg.get("label") or "")
        if not family:
            continue
        fraction = quota.get("remainingFraction")
        fraction = 0.0 if fraction is None else float(fraction)
        reset = to_ms(quota.get("resetTime"))
        best = pools.get(family)
        if best is None or (fraction, reset or 0) < (best[0], best[1] or 0):
            pools[family] = (fraction, reset)
    return [{"key": family, "label": family, "short": "g" if family == "Gemini" else "c",
             "percent": 100 - max(0.0, min(1.0, f)) * 100, "resetsAt": reset, "detail": None}
            for family, (f, reset) in sorted(pools.items())]


def plan_from_status(status):
    user = (status or {}).get("userStatus") or {}
    tier = (user.get("userTier") or {}).get("name")
    if tier:
        return tier
    info = (user.get("planStatus") or {}).get("planInfo") or {}
    for key in ("planDisplayName", "displayName", "productName", "planName", "planShortName"):
        if info.get(key):
            return info[key]
    return None


def fetch_local(pid, cmdline):
    csrf = flag(cmdline, "csrf_token")
    ext_port = flag(cmdline, "extension_server_port")
    ext_csrf = flag(cmdline, "extension_server_csrf_token")
    ports = [p for p in listening_ports(pid) if str(p) != ext_port]
    attempts = [("https", p, csrf) for p in ports if csrf]
    if ext_port:
        attempts += [("http", ext_port, t) for t in (ext_csrf, csrf) if t]

    last_error = None
    for scheme, port, token in attempts:
        try:
            status = call_local(port, token, "GetUserStatus", METADATA, scheme)
        except ProviderError as e:
            last_error = e
            continue
        plan = plan_from_status(status)
        try:
            limits = parse_summary(call_local(port, token, "RetrieveUserQuotaSummary",
                                              {"forceRefresh": True}, scheme))
        except ProviderError:
            limits = []
        if not limits:
            configs = (((status.get("userStatus") or {}).get("cascadeModelConfigData") or {})
                       .get("clientModelConfigs") or [])
            limits = parse_models(configs)
        if limits:
            return {"plan": plan, "limits": limits}
    if last_error:
        raise last_error
    return None


def fetch_remote():
    """Use the agy CLI's saved token (never refreshed here) with Cloud Code."""
    path = os.path.join(expand("~/.gemini/antigravity-cli"), "antigravity-oauth-token")
    try:
        token = read_json(path)["token"]
        access = token["access_token"]
    except (OSError, KeyError, ValueError, TypeError):
        return None
    expiry = to_ms(token.get("expiry"))
    if expiry and expiry < now_ms():
        return None
    headers = {"Authorization": f"Bearer {access}",
               "User-Agent": "antigravity/hub/2.9.1 linux/amd64"}
    hint = "Run `agy` or open Antigravity to log in again."
    info = http_json(CLOUD_URL + "loadCodeAssist", headers=headers, auth_hint=hint, body={
        "metadata": {"ideType": "ANTIGRAVITY", "platform": "PLATFORM_UNSPECIFIED",
                     "pluginType": "GEMINI"}})
    project = info.get("cloudaicompanionProject")
    if isinstance(project, dict):
        project = project.get("id") or project.get("projectId")
    body = {"project": project} if project else {}
    limits = parse_summary(http_json(CLOUD_URL + "retrieveUserQuotaSummary", headers=headers,
                                     body=body, auth_hint=hint))
    if not limits:
        return None
    plan = ((info.get("planInfo") or {}).get("planType")
            or (info.get("currentTier") or {}).get("name"))
    return {"plan": plan, "limits": limits}


def installed():
    config = xdg("XDG_CONFIG_HOME", "~/.config")
    return any(os.path.isdir(p) for p in (
        os.path.join(config, "Antigravity"), os.path.join(config, "Antigravity IDE"),
        expand("~/.antigravity"), expand("~/.gemini/antigravity-cli")))


def fetch(opts):
    errors = []
    for pid, cmdline in find_servers():
        try:
            result = fetch_local(pid, cmdline)
        except ProviderError as e:
            errors.append(e)
            continue
        if result:
            return result
    result = fetch_remote()
    if result:
        return result
    if errors:
        raise errors[0]
    if not installed():
        raise NotConfigured("Antigravity is not installed.")
    raise ProviderError("Antigravity isn't running. Open it to update the quota.")
