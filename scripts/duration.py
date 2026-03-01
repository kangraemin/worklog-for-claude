#!/usr/bin/env python3
"""세션 JSONL에서 durationMs를 합산하여 실제 Claude 작업 시간을 계산한다.

Usage:
    python3 ~/.claude/scripts/duration.py <snapshot_unix_timestamp> [project_cwd]

    snapshot_unix_timestamp: .worklogs/.snapshot의 timestamp (unix epoch)
    project_cwd: 프로젝트 경로 (기본: 현재 디렉토리)

Output:
    <total_seconds>,<total_minutes>
    예: 584.9,10
"""

import json
import glob
import os
import sys
from datetime import datetime, timezone


def encode_project_path(cwd: str) -> str:
    return cwd.replace("/", "-").replace(".", "-")


def find_latest_jsonl(project_dir: str) -> str | None:
    pattern = os.path.join(project_dir, "*.jsonl")
    files = sorted(glob.glob(pattern), key=os.path.getmtime, reverse=True)
    return files[0] if files else None


def sum_duration_ms(jsonl_path: str, after_iso: str) -> int:
    total_ms = 0
    with open(jsonl_path) as f:
        for line in f:
            try:
                obj = json.loads(line.strip())
                if obj.get("durationMs") and obj.get("timestamp", "") > after_iso:
                    total_ms += obj["durationMs"]
            except (json.JSONDecodeError, KeyError):
                continue
    return total_ms


def main():
    if len(sys.argv) < 2:
        print("Usage: duration.py <snapshot_unix_timestamp> [project_cwd]", file=sys.stderr)
        sys.exit(1)

    snapshot_ts = int(sys.argv[1])
    cwd = sys.argv[2] if len(sys.argv) > 2 else os.getcwd()

    # Convert unix timestamp to ISO for comparison
    after_iso = datetime.fromtimestamp(snapshot_ts, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")

    # Find JSONL
    encoded = encode_project_path(cwd)
    project_dir = os.path.expanduser(f"~/.claude/projects/{encoded}")

    if not os.path.isdir(project_dir):
        print("0,0")
        sys.exit(0)

    jsonl_path = find_latest_jsonl(project_dir)
    if not jsonl_path:
        print("0,0")
        sys.exit(0)

    total_ms = sum_duration_ms(jsonl_path, after_iso)
    total_sec = total_ms / 1000
    total_min = round(total_ms / 60000)

    print(f"{total_sec:.1f},{total_min}")


if __name__ == "__main__":
    main()
