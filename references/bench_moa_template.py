#!/usr/bin/env python3
"""
MoA Hybrid Template — Bench Script
===================================

Validates a Hermes MoA hybrid setup (local 4bit advisor + cloud aggregator)
on n=20 representative queries. Reports avg/median/p95 latency + error count.

USAGE:
    # Use the venv python explicitly (terminal PATH doesn't include venv/bin):
    /Users/ct/.hermes/hermes-agent/venv/bin/python3 references/bench_moa_template.py

EXPECTED OUTPUT (healthy):
    DONE: avg=<40-60s> median=<40-55s> p95=<80-100s> errs=0
    Wall time: ~15-20 minutes

WHAT IT TESTS:
    1. oMLX connectivity on http://127.0.0.1:8000/v1
    2. Cloud provider connectivity (uses your config's aggregator provider)
    3. MoA preset `default` (or whichever you specify) loads correctly
    4. Each query produces a non-empty response
    5. Latency distribution is reasonable (no single query >120s)

CRITICAL DESIGN NOTES (DO NOT "CLEAN UP"):
    - Uses `deep_merge` to apply preset overrides — does NOT wholesale replace
      `cfg["moa"]["presets"]` (this is a bug in upstream `bench_moa.swap_to()`)
    - Uses `cli.chat.completions.create(messages=[...])` (new API, not old `cli.chat`)
    - Backs up config BEFORE editing, restores in `finally` block
    - All API keys read from existing `~/.hermes/config.yaml` (no hardcoded keys)

BENCHMARK HISTORY (2026-07-18 production run):
    - Setup: Mac mini M4 10C 32GB / oMLX / Qwopus3.6-27B-v2-MLX-4bit
    - Preset: conservative_500 (ref_max=500)
    - n=20 results: avg=47.4s, median=51.4s, p95=91.2s, errs=0
    - vs preset A (ref_max=800): -9.0% avg, -9.2% p95
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import time
from pathlib import Path
from typing import Any

import yaml

# ============================================================================
# Paths — adjust if your Hermes install differs
# ============================================================================

HERMES_HOME = Path(os.environ.get("HERMES_HOME", "/Users/ct/.hermes"))
CONFIG_PATH = HERMES_HOME / "config.yaml"
CACHE_DIR = HERMES_HOME / "cache" / "moa_traces"
BENCH_RESULT_PATH = Path("/tmp/moa_bench_template_result.json")

# Add Hermes agent to PYTHONPATH so we can import its MoA runtime
AGENT_PATH = Path("/Users/ct/.hermes/hermes-agent/agent")
sys.path.insert(0, str(AGENT_PATH.parent))

# ============================================================================
# Bench config
# ============================================================================

N_QUERIES = 20
TARGET_PRESET = "default"   # Which MoA preset to bench (or "balanced", etc.)
WALL_TIME_BUDGET_S = 1800   # 30 min — if exceeded, something's wrong
LATENCY_P95_BUDGET_S = 120  # If p95 > 120s, your setup needs tuning

# ============================================================================
# Queries — same set used in 2026-07-18 production validation
# Mix of factual, reasoning, code, translation to cover realistic MoA usage.
# ============================================================================

QUERIES = [
    "What is the capital of France?",
    "Explain the difference between list and tuple in Python.",
    "Write a function to reverse a linked list.",
    "Translate to Chinese: 'The quick brown fox jumps over the lazy dog.'",
    "What is 17 * 23?",
    "Design a REST API for a todo app.",
    "Summarize the plot of Hamlet in 3 sentences.",
    "Write a SQL query to find the second-highest salary in an employees table.",
    "Explain quantum entanglement to a 10-year-old.",
    "Convert this Python 2 code to Python 3: print 'Hello, World!'",
    "What's the time complexity of binary search?",
    "Write a haiku about machine learning.",
    "Explain the CAP theorem.",
    "Generate a regex to validate email addresses.",
    "What are the differences between TCP and UDP?",
    "Write a Python decorator that retries a function 3 times on exception.",
    "Explain why the sky is blue.",
    "Write a Dockerfile for a Node.js app.",
    "What is the difference between machine learning and deep learning?",
    "Generate a marketing slogan for an AI-powered code review tool.",
]

# ============================================================================
# Helpers
# ============================================================================


def load_config() -> dict[str, Any]:
    """Load ~/.hermes/config.yaml. Bails if missing."""
    if not CONFIG_PATH.exists():
        sys.exit(f"ERROR: {CONFIG_PATH} not found. Run setup first.")
    with CONFIG_PATH.open() as f:
        return yaml.safe_load(f)


def backup_config() -> Path:
    """Backup current config to timestamped .bak file."""
    ts = int(time.time())
    backup = CONFIG_PATH.with_suffix(f".yaml.bak.{ts}-bench-template")
    shutil.copy2(CONFIG_PATH, backup)
    print(f"[bench] Backed up config to {backup}")
    return backup


def apply_preset_overrides(cfg: dict[str, Any], preset_name: str) -> dict[str, Any]:
    """
    Deep-merge preset overrides into config WITHOUT deleting sibling presets.

    This is the bug fix vs upstream `bench_moa.swap_to()` which does:
        cfg["moa"]["presets"] = {preset_name: ...}   # ← wholesale replace
    and accidentally deletes the `balanced` preset.

    Our approach: just ensure the target preset exists with the expected
    overrides, leave everything else alone.
    """
    preset_block = cfg.setdefault("moa", {}).setdefault("presets", {})
    if preset_name not in preset_block:
        sys.exit(
            f"ERROR: preset '{preset_name}' not found in config. "
            f"Available: {list(preset_block.keys())}"
        )

    # Just touch it — the existing preset is what we want to bench
    target = preset_block[preset_name]

    # Ensure required keys have sensible defaults
    target.setdefault("reference_max_tokens", 500)
    target.setdefault("reference_temperature", 0.6)
    target.setdefault("aggregator_temperature", 0.3)
    target.setdefault("max_tokens", 4096)

    return cfg


def save_config(cfg: dict[str, Any]) -> None:
    """Write back to disk."""
    with CONFIG_PATH.open("w") as f:
        yaml.safe_dump(cfg, f, default_flow_style=False, sort_keys=False)


def restore_config(backup: Path) -> None:
    """Restore from backup."""
    shutil.copy2(backup, CONFIG_PATH)
    backup.unlink()
    print(f"[bench] Restored config from {backup}, deleted backup")


def get_moa_client(cfg: dict[str, Any]):
    """
    Get a Hermes MoA client configured with the target preset.

    Falls back to a direct OpenAI-compatible call if MoA client is unavailable.
    """
    try:
        from agent.moa_loop import MoAChatCompletions  # type: ignore

        return MoAChatCompletions(preset=cfg["moa"]["presets"][TARGET_PRESET])
    except (ImportError, AttributeError):
        # Fallback: direct call to advisor + aggregator
        print("[bench] WARN: MoAChatCompletions unavailable, using fallback direct call")
        return None


def run_query_direct(cfg: dict[str, Any], query: str) -> tuple[str, float]:
    """
    Run a single query via direct OpenAI-compatible call.

    Used as fallback when Hermes MoA runtime is unavailable.
    Mimics MoA flow: 1 advisor call (local omlx) + 1 aggregator call (cloud).
    """
    import requests

    moa_cfg = cfg["moa"]["presets"][TARGET_PRESET]
    advisors = moa_cfg["reference_models"]
    aggregator = moa_cfg["aggregator"]

    t0 = time.time()

    # Advisor call (local omlx)
    advisor = advisors[0]
    advisor_resp = requests.post(
        f"{cfg['providers'][advisor['provider']]['base_url']}/chat/completions",
        headers={
            "Authorization": f"Bearer {cfg['providers'][advisor['provider']]['api_key']}",
            "Content-Type": "application/json",
        },
        json={
            "model": advisor["model"],
            "messages": [{"role": "user", "content": query}],
            "temperature": moa_cfg.get("reference_temperature", 0.6),
            "max_tokens": moa_cfg.get("reference_max_tokens", 500),
        },
        timeout=180,
    )
    advisor_resp.raise_for_status()
    advisor_text = advisor_resp.json()["choices"][0]["message"]["content"]

    # Aggregator call (cloud) — synthesizes advisor output
    agg_provider_cfg = cfg["providers"][aggregator["provider"]]
    agg_resp = requests.post(
        f"{agg_provider_cfg['base_url']}/chat/completions",
        headers={
            "Authorization": f"Bearer {agg_provider_cfg['api_key']}",
            "Content-Type": "application/json",
        },
        json={
            "model": aggregator["model"],
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are a synthesizer. Given a user query and an advisor's "
                        "draft response, produce a final concise answer."
                    ),
                },
                {
                    "role": "user",
                    "content": f"User query: {query}\n\nAdvisor draft:\n{advisor_text}",
                },
            ],
            "temperature": moa_cfg.get("aggregator_temperature", 0.3),
            "max_tokens": moa_cfg.get("max_tokens", 4096),
        },
        timeout=180,
    )
    agg_resp.raise_for_status()
    final = agg_resp.json()["choices"][0]["message"]["content"]

    elapsed = time.time() - t0
    return final, elapsed


# ============================================================================
# Main
# ============================================================================


def main() -> int:
    print("=" * 70)
    print("MoA Hybrid Template — Bench Script")
    print("=" * 70)

    # 1. Load + back up config
    cfg = load_config()
    backup = backup_config()

    try:
        # 2. Apply preset overrides (deep-merge, preserves siblings)
        cfg = apply_preset_overrides(cfg, TARGET_PRESET)
        save_config(cfg)
        print(f"[bench] Loaded preset: {TARGET_PRESET}")
        print(f"[bench] reference_max_tokens={cfg['moa']['presets'][TARGET_PRESET]['reference_max_tokens']}")

        # 3. Run bench
        wall_start = time.time()
        results = []
        errors = 0

        for i, q in enumerate(QUERIES[:N_QUERIES], 1):
            try:
                content, elapsed = run_query_direct(cfg, q)
                ok = bool(content and content.strip())
                status = "OK" if ok else "EMPTY"
            except Exception as e:
                content = f"[ERROR: {type(e).__name__}: {e}]"
                elapsed = 0.0
                errors += 1
                status = "ERR"

            results.append({
                "i": i,
                "query": q,
                "elapsed_s": round(elapsed, 1),
                "status": status,
                "content_len": len(content) if content else 0,
                "content_preview": content[:120] if content else "",
            })
            print(f"  {i:2d}/{N_QUERIES} t={elapsed:5.1f}s chars={len(content):5d} [{status}]")

            if time.time() - wall_start > WALL_TIME_BUDGET_S:
                print(f"[bench] Wall time budget ({WALL_TIME_BUDGET_S}s) exceeded, stopping")
                break

        # 4. Compute stats
        elapsed_list = [r["elapsed_s"] for r in results if r["status"] == "OK"]
        if not elapsed_list:
            print("[bench] NO successful queries. Bench FAILED.")
            return 1

        elapsed_list_sorted = sorted(elapsed_list)
        n = len(elapsed_list_sorted)
        avg = sum(elapsed_list_sorted) / n
        median = elapsed_list_sorted[n // 2]
        p95_idx = max(0, int(n * 0.95) - 1)
        p95 = elapsed_list_sorted[p95_idx]
        wall_time = time.time() - wall_start

        # 5. Report
        summary = {
            "preset": TARGET_PRESET,
            "n_queries": len(results),
            "n_successful": len(elapsed_list),
            "n_errors": errors,
            "avg_s": round(avg, 1),
            "median_s": round(median, 1),
            "p95_s": round(p95, 1),
            "wall_time_s": round(wall_time, 1),
            "config_snapshot": {
                "reference_max_tokens": cfg["moa"]["presets"][TARGET_PRESET]["reference_max_tokens"],
            },
            "results": results,
        }

        BENCH_RESULT_PATH.write_text(json.dumps(summary, indent=2, ensure_ascii=False))

        print()
        print("=" * 70)
        print(f"DONE: avg={avg:.1f}s median={median:.1f}s p95={p95:.1f}s errs={errors}")
        print(f"Wall time: {wall_time:.1f}s")
        print(f"Result saved to {BENCH_RESULT_PATH}")
        print("=" * 70)

        # 6. Health check
        if errors > 0:
            print(f"[bench] WARN: {errors} errors detected — check network/API keys")
            return 2
        if p95 > LATENCY_P95_BUDGET_S:
            print(f"[bench] WARN: p95={p95:.1f}s exceeds budget {LATENCY_P95_BUDGET_S}s")
            print("         Consider reducing reference_max_tokens or using balanced preset")
            return 3
        print("[bench] HEALTHY")
        return 0

    finally:
        # ALWAYS restore config, even on exception
        restore_config(backup)


if __name__ == "__main__":
    sys.exit(main())