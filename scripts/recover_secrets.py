"""Recover legacy data/secrets.json into config.json.

Usage:
    # If STORYFORGE_SECRET_KEY env was set when secrets.json was written:
    set STORYFORGE_SECRET_KEY=<your-key>
    python scripts/recover_secrets.py

    # Otherwise, try common defaults / blank — the script reports what it finds.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.secret_manager import load_encrypted
from config import ConfigManager

SECRETS_FILE = "data/secrets.json"


def main() -> int:
    if not os.path.exists(SECRETS_FILE):
        print(f"No {SECRETS_FILE} found — nothing to recover.")
        return 0
    if not os.environ.get("STORYFORGE_SECRET_KEY"):
        print("STORYFORGE_SECRET_KEY is not set — set it to the original key first.")
        print("If you never set one, the file may already be plaintext JSON.")
    data = load_encrypted(SECRETS_FILE)
    if not data:
        print("Decryption produced empty result — wrong key, or file is corrupt.")
        return 1
    print("Recovered fields:")
    for section, fields in data.items():
        for k, v in (fields or {}).items():
            mask = (str(v)[:6] + "***" + str(v)[-4:]) if isinstance(v, str) and len(str(v)) > 10 else "<value>"
            if isinstance(v, list):
                mask = f"<list len={len(v)}>"
            print(f"  {section}.{k} = {mask}")
    cfg = ConfigManager()
    for k, v in data.get("llm", {}).items():
        if hasattr(cfg.llm, k) and v:
            setattr(cfg.llm, k, v)
    for k, v in data.get("pipeline", {}).items():
        if hasattr(cfg.pipeline, k) and v:
            setattr(cfg.pipeline, k, v)
    cfg.save()
    os.rename(SECRETS_FILE, SECRETS_FILE + ".migrated")
    print(f"\nMerged into data/config.json. Archived legacy file as {SECRETS_FILE}.migrated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
