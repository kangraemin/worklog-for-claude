#!/usr/bin/env python3
"""프로젝트 JSONL에서 토큰 사용량과 비용을 계산한다.

Usage:
    python3 ~/.claude/scripts/token-cost.py <snapshot_unix_timestamp> [project_cwd]

    snapshot_unix_timestamp: ~/.claude/worklogs/.snapshot의 timestamp (unix epoch, 0이면 전체)
    project_cwd: 프로젝트 경로 (기본: 현재 디렉토리)

Output:
    <total_tokens>,<total_cost>
    예: 52340,0.234
"""

import json
import glob
import os
import sys
from datetime import datetime, timezone

# 모델별 단가 (USD per 1M tokens)
# https://docs.anthropic.com/en/docs/about-claude/models
PRICING = {
    "claude-opus-4-6": {
        "input": 15.0,
        "output": 75.0,
        "cache_read": 1.5,
        "cache_creation": 18.75,
    },
    "claude-sonnet-4-6": {
        "input": 3.0,
        "output": 15.0,
        "cache_read": 0.30,
        "cache_creation": 3.75,
    },
    "claude-haiku-4-5": {
        "input": 0.80,
        "output": 4.0,
        "cache_read": 0.08,
        "cache_creation": 1.0,
    },
}

# 모델 이름 정규화 (claude-sonnet-4-6-20250514 → claude-sonnet-4-6)
def normalize_model(model: str) -> str:
    for key in PRICING:
        if model.startswith(key):
            return key
    return model


def encode_project_path(cwd: str) -> str:
    return cwd.replace("/", "-").replace(".", "-")


def calc_cost(model: str, usage: dict) -> float:
    pricing = PRICING.get(normalize_model(model))
    if not pricing:
        return 0.0

    input_tokens = usage.get("input_tokens", 0)
    output_tokens = usage.get("output_tokens", 0)
    cache_read = usage.get("cache_read_input_tokens", 0)
    cache_creation = usage.get("cache_creation_input_tokens", 0)

    cost = (
        input_tokens * pricing["input"]
        + output_tokens * pricing["output"]
        + cache_read * pricing["cache_read"]
        + cache_creation * pricing["cache_creation"]
    ) / 1_000_000

    return cost


def process_jsonl(jsonl_path: str, after_iso: str) -> tuple[int, float]:
    total_tokens = 0
    total_cost = 0.0

    with open(jsonl_path) as f:
        for line in f:
            try:
                obj = json.loads(line.strip())
                if obj.get("type") != "assistant":
                    continue
                ts = obj.get("timestamp", "")
                if ts <= after_iso:
                    continue

                msg = obj.get("message", {})
                model = msg.get("model", "")
                usage = msg.get("usage", {})

                tokens = (
                    usage.get("input_tokens", 0)
                    + usage.get("output_tokens", 0)
                    + usage.get("cache_read_input_tokens", 0)
                    + usage.get("cache_creation_input_tokens", 0)
                )
                total_tokens += tokens
                total_cost += calc_cost(model, usage)
            except (json.JSONDecodeError, KeyError):
                continue

    return total_tokens, total_cost


def main():
    if len(sys.argv) < 2:
        print("Usage: token-cost.py <snapshot_unix_timestamp> [project_cwd]", file=sys.stderr)
        sys.exit(1)

    snapshot_ts = int(sys.argv[1])
    cwd = sys.argv[2] if len(sys.argv) > 2 else os.getcwd()

    if snapshot_ts == 0:
        after_iso = ""
    else:
        after_iso = datetime.fromtimestamp(snapshot_ts, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")

    encoded = encode_project_path(cwd)
    project_dir = os.path.expanduser(f"~/.claude/projects/{encoded}")

    if not os.path.isdir(project_dir):
        print("0,0.000")
        sys.exit(0)

    pattern = os.path.join(project_dir, "*.jsonl")
    jsonl_files = glob.glob(pattern)

    if not jsonl_files:
        print("0,0.000")
        sys.exit(0)

    grand_tokens = 0
    grand_cost = 0.0

    for jsonl_path in jsonl_files:
        tokens, cost = process_jsonl(jsonl_path, after_iso)
        grand_tokens += tokens
        grand_cost += cost

    print(f"{grand_tokens},{grand_cost:.3f}")


if __name__ == "__main__":
    main()
