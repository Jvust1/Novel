from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from novel_ai.integrations import probe_integrations


def main() -> int:
    rows = probe_integrations()
    installed = [row for row in rows if row["installed"] is True]
    missing = [row for row in rows if row["installed"] is False]
    modes = Counter(row["mode"] for row in rows)

    print(f"Novel open-source integrations: {len(rows)}")
    print("Modes:", ", ".join(f"{k}={v}" for k, v in sorted(modes.items())))
    print(f"Optional Python integrations installed: {len(installed)}")
    for row in installed:
        print(f"  OK   {row['key']:<22} {row['repository']}")
    if missing:
        print(f"Optional Python integrations not installed: {len(missing)}")
        for row in missing:
            print(f"  MISS {row['key']:<22} {row['package'] or row['repository']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
