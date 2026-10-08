"""Single entry point. Task definitions live in configs/tasks.json; no model calls on import."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def build_command(task: str, config: dict, extra: list[str]) -> list[str]:
    spec = config["tasks"][task]
    script = (ROOT / spec["script"]).resolve()
    if not script.is_relative_to(ROOT / "scripts") or not script.is_file():
        raise ValueError("Task script must exist inside scripts/")
    if extra and extra[0] == "--":
        extra = extra[1:]
    return [sys.executable, "-s", str(script), *spec.get("args", []), *extra]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("task", nargs="?")
    parser.add_argument("--list", action="store_true")
    parser.add_argument("--dry-run", action="store_true", help="Print the command; do not execute")
    parser.add_argument("--config", type=Path, default=ROOT / "configs/tasks.json")
    args, extra = parser.parse_known_args()
    config = json.loads(args.config.read_text(encoding="utf-8-sig"))
    if args.list or args.task is None:
        for name, spec in config["tasks"].items():
            print(f"{name}: {spec['description']} [{spec['execution']}]")
        return 0
    if args.task not in config["tasks"]:
        parser.error(f"Unknown task: {args.task}; use --list")
    command = build_command(args.task, config, extra)
    print(subprocess.list2cmdline(command), flush=True)
    if args.dry_run:
        return 0
    return subprocess.run(command, cwd=ROOT, check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main())
