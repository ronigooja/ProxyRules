#!/usr/bin/env python3
"""Publish generated subscription templates to one XBoard environment."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = {
    "subscribe_template_singbox": ROOT / "XBoard/singbox.json",
    "subscribe_template_clash": ROOT / "XBoard/clash.yaml",
    "subscribe_template_clashmeta": ROOT / "XBoard/clashmeta.yaml",
    "subscribe_template_stash": ROOT / "XBoard/stash.yaml",
    "subscribe_template_surge": ROOT / "XBoard/surge.conf",
    "subscribe_template_surfboard": ROOT / "XBoard/surfboard.conf",
}


def equivalent(key: str, existing: object, desired: str) -> bool:
    if not isinstance(existing, str):
        return False
    if key == "subscribe_template_singbox":
        try:
            return json.loads(existing) == json.loads(desired)
        except json.JSONDecodeError:
            return False
    # XBoard's TrimStrings middleware removes surrounding whitespace on save.
    return existing.strip() == desired.strip()


def required(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise ValueError(f"missing {name} in the selected GitHub Environment")
    return value


def request(url: str, token: str, payload: dict[str, str] | None = None) -> dict:
    data = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = Request(url, data=data, headers={
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
        "Content-Type": "application/json",
        "User-Agent": "ProxyRules monthly publisher",
    })
    try:
        with urlopen(req, timeout=45) as response:
            result = json.load(response)
    except HTTPError as exc:
        raise RuntimeError(f"XBoard API returned HTTP {exc.code}") from None
    except URLError as exc:
        raise RuntimeError(f"XBoard API connection failed: {exc.reason}") from None
    if not isinstance(result, dict) or "data" not in result:
        raise RuntimeError("XBoard API returned an unexpected response")
    return result


def main() -> None:
    base = required("XBOARD_API_URL").rstrip("/")
    parsed = urlparse(base)
    if (parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password
            or parsed.path not in ("", "/") or parsed.query or parsed.fragment):
        raise ValueError("XBOARD_API_URL must be an HTTPS origin without an API path")
    admin_path = required("XBOARD_ADMIN_PATH").strip("/")
    if not re.fullmatch(r"[A-Za-z0-9_-]+", admin_path):
        raise ValueError("XBOARD_ADMIN_PATH must be one path segment")
    token = required("XBOARD_ADMIN_TOKEN").removeprefix("Bearer ")

    payload = {key: path.read_text(encoding="utf-8") for key, path in TEMPLATES.items()}
    if not all(payload.values()):
        raise ValueError("generated XBoard templates are empty")
    endpoint = f"{base}/api/v2/{admin_path}/config"
    current = request(f"{endpoint}/fetch?key=subscribe_template", token)
    current_templates = current["data"].get("subscribe_template")
    if not isinstance(current_templates, dict):
        raise RuntimeError("XBoard did not return subscription templates")
    changed = {key: value for key, value in payload.items()
               if not equivalent(key, current_templates.get(key), value)}
    if not changed:
        print(f"{parsed.netloc}: subscription templates are current")
        return
    response = request(f"{endpoint}/save", token, changed)
    if response.get("data") is not True:
        raise RuntimeError("XBoard did not confirm template update")
    saved = request(f"{endpoint}/fetch?key=subscribe_template", token)["data"].get("subscribe_template")
    if not isinstance(saved, dict) or any(
            not equivalent(key, saved.get(key), value) for key, value in payload.items()):
        raise RuntimeError("XBoard template readback did not match generated files")
    print(f"{parsed.netloc}: updated {', '.join(changed)}")


if __name__ == "__main__":
    main()
