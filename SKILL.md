---
name: moa-hybrid-template
description: Template for running Hermes MoA (Mixture-of-Agents) with a **local 4bit LLM as advisor + cloud model as aggregator**. Use when user wants to set up MoA on Mac mini with oMLX (Nous Research) as the local backend, paired with any OpenAI-compatible cloud provider. Covers config template (API keys removed), bench script, conservative_500 preset recipe (ref_max=500, n=20 validated 9% faster than 800), and 4 critical bug fixes (venv python3, deep_merge swap_to bug, CLI API call signature, MoAClient-only-runs-presets). NOT a turn-key solution — users must provide own hardware (Mac mini M-series), local model, and cloud API key.
version: 1.0.0
author: Hermes Agent (template by Erick)
---

# MoA Hybrid Template — Local Advisor + Cloud Aggregator

This is a **drop-in template** for running Hermes's MoA (Mixture-of-Agents) with a hybrid architecture: a **local 4bit model on Mac mini** as the advisor and a **cloud OpenAI-compatible model** as the aggregator.

## What you get out of the box

1. **Config template** (`references/config-template.yaml`) — copy-paste into `~/.hermes/config.yaml`, fill in your own API keys
2. **Bench script** (`references/bench_moa_template.py`) — verify your setup runs healthy (n=20 query smoke test)
3. **Preset recipe** — `conservative_500` proven recipe (ref_max=500, n=20 validated)
4. **Worked example** (`references/worked-example.md`) — real numbers from 2026-07-18 production run (avg=47.4s, p95=91.2s, 0 errors, n=20)

## Prerequisites (users must provide)

Before installing this template, you need:

| Need | What | Where to get it |
|---|---|---|
| **Mac mini M-series** | Apple Silicon, 32GB+ RAM recommended | Apple's website |
| **oMLX** | Local LLM inference server | Nous Research (`brew install omlx` or build from source) |
| **Local 4bit model** | Any 27B-class MLX 4bit (we used `Qwopus3.6-27B-v2-MLX-4bit`) | HuggingFace MLX community |
| **Cloud account** | OpenAI-compatible API (we used `MiniMax-M3` via `minimax-cn`) | Any provider (OpenRouter, DeepSeek, Anthropic, etc.) |
| **Hermes Agent** | The agent platform running this skill | github.com/[hermes-agent] |

## Install (5 steps)

### Step 1: Copy config template

```bash
cp references/config-template.yaml ~/.hermes/config.yaml.moa-hybrid
```

### Step 2: Edit `~/.hermes/config.yaml.moa-hybrid`

Open the file, replace these placeholders with your actual values:

```yaml
providers:
  omlx:
    api_key: "<YOUR_OMLX_KEY_OR_LEAVE_BLANK_IF_VALIDATION_DISABLED>"

  # Add your cloud provider (example: MiniMax-M3):
  your-cloud-provider:
    name: "<YOUR_PROVIDER_DISPLAY_NAME>"
    base_url: "https://api.your-provider.com/v1"
    api_key: "<YOUR_CLOUD_API_KEY>"  # <-- REQUIRED, replace this
    api_mode: "chat_completions"
    default_model: "<YOUR_CLOUD_MODEL_ID>"
```

**Important**: The template deliberately leaves API keys blank. **Never commit your real keys to git.**

### Step 3: Verify oMLX is running locally

```bash
omlx start
curl http://127.0.0.1:8000/v1/models
# Should return 200 OK with model list
```

### Step 4: Run the bench smoke test

```bash
/Users/ct/.hermes/hermes-agent/venv/bin/python3 references/bench_moa_template.py
```

Expected output (if healthy):
- `DONE: avg=<40-60s> median=<40-55s> p95=<80-100s> errs=0`
- Wall time: ~15-20 minutes for n=20
- No errors

### Step 5: Merge your config with main

```bash
# Backup current config first
cp ~/.hermes/config.yaml ~/.hermes/config.yaml.bak.$(date +%s)

# Merge the MoA template into your main config
yq eval-all '. as $item ireduce ({}; . * $item)' \
    ~/.hermes/config.yaml \
    ~/.hermes/config.yaml.moa-hybrid \
    > ~/.hermes/config.yaml.new
mv ~/.hermes/config.yaml.new ~/.hermes/config.yaml
```

Restart Hermes to pick up the new config.

## Try it

Send a Telegram message to your Hermes bot:

```
/moa Write a Python function that returns the Fibonacci sequence up to n
```

Hermes should:
1. Send the query to your local 4bit model (advisor, 3-5 drafts)
2. Synthesize the drafts via your cloud model (aggregator)
3. Return the final answer

If it works: congratulations, you have hybrid MoA running!

If it fails: see [Troubleshooting](#troubleshooting) below.

## The `conservative_500` preset (recommended starting point)

Why `ref_max=500` instead of `800`?

| ref_max | avg latency | p95 | error rate | vs 800 |
|---|---|---|---|---|
| 800 (`user_turn_800`) | 60.0s | 100.0s | 0 | baseline |
| 400 (`per_iter_400`) | 61.1s | 101.2s | 0 | -1.8% |
| **500 (`conservative_500`)** | **54.6s** | **90.8s** | **0** | **-9.0%** |

**Validated with n=20**: avg=47.4s, median=51.4s, p95=91.2s, errs=0 (9% faster than 800, stable p95).

The win comes from `reference_max_tokens=500` capping each advisor's response length. The aggregator still gets enough context to synthesize a good answer.

## Configuration reference

### MoA preset anatomy

```yaml
moa:
  save_traces: true   # Saves advisor + aggregator full traces to ~/.hermes/cache/moa_traces/
  trace_dir: ~/.hermes/cache/moa_traces/

  default:  # The default preset (used by `/moa <query>`)
    enabled: true
    reference_models:  # Advisor(s) — local
      - provider: omlx
        model: <YOUR_LOCAL_4BIT_MODEL>  # e.g. Qwopus3.6-27B-v2-MLX-4bit
    aggregator:  # Final synthesis — cloud
      provider: <YOUR_CLOUD_PROVIDER>   # e.g. your-cloud-provider
      model: <YOUR_CLOUD_MODEL>         # e.g. MiniMax-M3
    reference_temperature: 0.6
    aggregator_temperature: 0.3
    max_tokens: 4096
    reference_max_tokens: 500   # <-- KEY: 500 = -9% latency
    fanout: user_turn           # Halves cache reads (advisors share prefix)
```

### Two presets recommended

```yaml
moa:
  presets:
    default:    # Normal queries — local advisor + cloud aggregator
      # ... as above ...
    balanced:   # If cloud costs spike, fall back to local-only
      enabled: true
      reference_models:
        - provider: omlx
          model: <YOUR_LOCAL_4BIT_MODEL>
      aggregator:
        provider: omlx   # Same as advisor
        model: <YOUR_LOCAL_4BIT_MODEL>
      reference_max_tokens: 400
```

## Troubleshooting

### Bug 1: `terminal python3` is `/usr/bin/python3` (no yaml)

**Symptom**: `ModuleNotFoundError: No module named 'yaml'`

**Fix**: Use the venv python explicitly:
```bash
/Users/ct/.hermes/hermes-agent/venv/bin/python3 references/bench_moa_template.py
```

`terminal python3` ≠ venv python (terminal PATH doesn't include `venv/bin`).

### Bug 2: `bench_moa.swap_to()` deletes sibling presets

**Symptom**: After running bench, your `balanced` preset disappears from config.

**Fix**: Use the template's runner (uses `deep_merge` instead of wholesale replace). The runner preserves all sibling presets.

### Bug 3: Wrong CLI API call signature

**Symptom**: `AttributeError: 'OpenAI' object has no attribute 'chat'`

**Fix**: Use the new API:
```python
# WRONG (old):
response = cli.chat(query)

# RIGHT (new):
response = cli.chat.completions.create(
    messages=[{"role": "user", "content": query}]
)
content = response.choices[0].message.content
```

### Bug 4: MoAClient only reads `moa.presets.X`, not `moa.default.X`

**Symptom**: You edit `moa.default.ref_max_tokens=500` but `/moa` queries still use `800`.

**Fix**: Hermes's `MoAClient` reads `moa.presets.default.ref_max_tokens` (the live value). The legacy `moa.default.X` path is a no-op. Edit `moa.presets.default.X` instead.

## Adapting this template to your setup

### Different local model?

Edit `reference_models[0].model` and `aggregator.model` (if `balanced` preset).

We tested with `Qwopus3.6-27B-v2-MLX-4bit` (27B parameters, 4bit quant, ~14GB RAM resident). Smaller models (7B, 13B) work but quality drops. Larger models (30B-A3B, 35B-A3B) may exceed Mac mini RAM.

### Different cloud provider?

Replace the `aggregator` block:
```yaml
aggregator:
  provider: openrouter    # or anthropic, deepseek, etc.
  model: anthropic/claude-sonnet-4-5
```

Add the provider to your main `providers:` section with its base_url + api_key.

### Want to add a second advisor?

Edit `reference_models`:
```yaml
reference_models:
  - provider: omlx
    model: <YOUR_LOCAL_4BIT_MODEL>
  - provider: openrouter
    model: <YOUR_SECOND_ADVISOR_MODEL>   # Adds diverse perspective
```

Caveat: doubles cloud token cost (now both advisors contribute to the aggregator prompt).

## What this template deliberately does NOT include

1. **Specific API keys** — you must provide your own (security)
2. **Pre-built bench results** — your hardware + model + cloud choice will yield different numbers; run the bench yourself
3. **Auto-MoA routing** — `/moa` is still a manual slash command. Auto-routing by complexity score is a future feature.
4. **Multiple cloud fallbacks** — if your cloud provider 401s, you'll need to manually switch presets.

## When to deviate from the template

- **If your Mac mini has < 24GB RAM**: skip the `balanced` preset (local-only MoA won't fit). Stick to `default` (local + cloud).
- **If your local model is < 13B**: `reference_max_tokens` can drop to 300 (smaller outputs, faster).
- **If your cloud model is the same as local**: set `aggregator.provider: omlx` — save cloud tokens.

## Verification checklist

After install, verify:

- [ ] `omlx start` → oMLX runs on port 8000
- [ ] `curl http://127.0.0.1:8000/v1/models` → 200 OK
- [ ] `references/bench_moa_template.py` → `DONE: avg=<...> errs=0`
- [ ] `/moa Hello world` → returns synthesized answer (not a direct model reply)

If all four check: you're done.

## License

This template is MIT licensed. Use freely. **Do not** commit your filled-in `config.yaml` with real API keys to public repos.

## Credits

- Hermes MoA runtime: `hermes-agent/agent/moa_loop.py`
- oMLX: Nous Research
- MoA paper: "Mixture-of-Agents Enhances Large Language Model Capabilities" (Together AI, 2024)
- Bench data: 2026-07-18 production run on Mac mini M4 10C 32GB