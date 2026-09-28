#!/usr/bin/env python3
"""Fetch the upstream Shadowrocket profile and add this repository's rules."""

from pathlib import Path
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
UPSTREAM_URL = "https://cf.buliang0.cf/shadowrocket-rules/nodnsleak-pk.ini"
OUTPUT = ROOT / "Shadowrocket" / "nodnsleak-pk.ini"
LOCAL_RULE_FILES = (ROOT / "Rules" / "ChinaAI.list", ROOT / "Rules" / "DirectIP.list")
BEGIN = "# >>> ProxyRules local rules >>>"
END = "# <<< ProxyRules local rules <<<"


def local_rules() -> str:
    lines = [BEGIN]
    for path in LOCAL_RULE_FILES:
        lines.append(f"# Source: {path.relative_to(ROOT)}")
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip() and not line.lstrip().startswith("#"):
                lines.append(line)
        lines.append("")
    lines.append(END)
    return "\n".join(lines)


def merge(upstream: str) -> str:
    lines = upstream.replace("\r\n", "\n").splitlines()
    try:
        rule_header = next(i for i, line in enumerate(lines) if line.strip().lower() == "[rule]")
    except StopIteration as exc:
        raise ValueError("upstream profile does not contain a [Rule] section") from exc

    # The local block is placed first so the repository's explicit rules win.
    block = local_rules().splitlines()
    merged = lines[: rule_header + 1] + [""] + block + [""] + lines[rule_header + 1 :]
    return "\n".join(merged).rstrip() + "\n"


def main() -> None:
    request = Request(UPSTREAM_URL, headers={"User-Agent": "ProxyRules updater"})
    with urlopen(request, timeout=60) as response:
        upstream = response.read().decode("utf-8-sig")
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(merge(upstream), encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
