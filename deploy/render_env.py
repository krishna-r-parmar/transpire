#!/usr/bin/env python3
"""Assemble explicitly mapped GitHub secrets into a private PutParameter request."""

import json
import os
from pathlib import Path
import re
import sys


def build_request(environ):
    domain = environ.get("CFG_APP_DOMAIN", "").strip()
    if not re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?", domain):
        raise ValueError("Set APP_DOMAIN to the public hostname, without https:// or a path")

    settings = {}
    template = Path(__file__).with_name("transpire.env.example").read_text()
    for line in template.splitlines():
        if line and not line.startswith("#"):
            key, value = line.split("=", 1)
            settings[key] = value

    settings.update(
        DATABASE_URL="",
        OUTBOX_ENCRYPTION_KEY="",
        ALLOWED_HOSTS=f"{domain},localhost,127.0.0.1",
        CORS_ORIGINS=f"https://{domain}",
        PUBLIC_APP_URL=f"https://{domain}",
        PUBLIC_API_URL=f"https://{domain}/api/v1",
        NEXT_PUBLIC_API_URL=f"https://{domain}/api/v1",
        EMAIL_FROM_ADDRESS=f"no-reply@{domain}",
    )
    for key in settings:
        override = environ.get(f"CFG_{key}", "")
        if override:
            settings[key] = override

    missing = [key for key in ("DATABASE_URL", "OUTBOX_ENCRYPTION_KEY") if not settings[key].strip()]
    if missing:
        raise ValueError("Add repository secrets: " + ", ".join(missing))

    # Compose parses double-quoted escapes and treats $$ as a literal dollar.
    # Values enter through environment variables, never executable shell text.
    value = "".join(
        f"{key}={json.dumps(item.replace('$', '$$'), ensure_ascii=False)}\n"
        for key, item in settings.items()
    )
    if len(value.encode("utf-8")) > 4096:
        raise ValueError("Generated configuration exceeds the 4096-byte Standard parameter limit")
    return {
        "Name": environ["ENV_PARAMETER"],
        "Value": value,
        "Type": "SecureString",
        "KeyId": "alias/aws/ssm",
        "Tier": "Standard",
        "Overwrite": True,
    }


if __name__ == "__main__":
    try:
        request = build_request(os.environ)
    except ValueError as error:
        sys.exit(f"::error::{error}")
    json.dump(request, sys.stdout)
