#!/usr/bin/env python3
"""Configure scoped Codex egress for the Hermes gateway.

Both v3 Hermes kits call this at sandbox startup. Hermes loads its user .env
with override=True, including when a new gateway is started independently of
the CLI. Only chatgpt.com bypasses the HTTP proxy; other providers keep their
existing proxy-managed behavior. The network-policy allowlist remains enforced
by the sandbox independently of NO_PROXY.
"""

from __future__ import annotations

import os
from pathlib import Path
import re
import sys
import tempfile

HOST = "chatgpt.com"
KEYS = ("NO_PROXY", "no_proxy")
LOOPBACK = ("localhost", "127.0.0.1", "::1")
ASSIGNMENT = re.compile(r"^(\s*(?:export\s+)?)(NO_PROXY|no_proxy)(\s*=\s*)(.*)$")


def split_setting(raw: str) -> tuple[str, str, str]:
    """Return (value, quote, trailing_comment) for a simple dotenv assignment."""
    raw = raw.strip()
    if raw.startswith(("'", '"')):
        quote = raw[0]
        end = raw.find(quote, 1)
        if end != -1:
            return raw[1:end], quote, raw[end + 1 :]
    match = re.match(r"^(.*?)(\s+#.*)?$", raw)
    return match.group(1), "", match.group(2) or ""


def merge_entries(*values: str) -> str:
    entries: list[str] = []
    seen: set[str] = set()
    for value in values:
        for entry in re.split(r"[,\s]+", value):
            entry = entry.strip()
            if entry and entry.lower() not in seen:
                entries.append(entry)
                seen.add(entry.lower())
    if "*" in seen:
        return ",".join(entries)  # existing wildcard already bypasses Codex
    for host in (*LOOPBACK, HOST):
        if host not in seen:
            entries.append(host)
            seen.add(host)
    return ",".join(entries)


def configure(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    original = path.read_text(encoding="utf-8") if path.exists() else ""
    lines = original.splitlines()

    # Preserve both spellings. The v3 lifecycle hook declares these env names,
    # since hooks otherwise receive a deny-by-default environment.
    values = [os.environ.get(key, "") for key in KEYS]
    matches = []
    for i, line in enumerate(lines):
        m = ASSIGNMENT.match(line)
        if m:
            value, quote, comment = split_setting(m.group(4))
            values.append(value)
            matches.append((i, m, quote, comment))

    merged = merge_entries(*values)
    covered: set[str] = set()
    for i, m, quote, comment in matches:
        key = m.group(2)
        covered.add(key)
        lines[i] = f"{m.group(1)}{key}{m.group(3)}{quote}{merged}{quote}{comment}"
    for key in KEYS:
        if key not in covered:
            lines.append(f"{key}={merged}")

    updated = "\n".join(lines) + "\n"
    if updated == original:
        return

    # Atomic replacement and owner-only permissions. Never log any .env data.
    fd, name = tempfile.mkstemp(prefix=".env.codex-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as out:
            out.write(updated)
        os.chmod(name, 0o600)
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


if __name__ == "__main__":
    home = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.home() / ".hermes"
    configure(home / ".env")
