---
project: moa-hybrid-template
category: hermes-skill-template
status: production
tested_on: mac-mini-m4-2026-07-18
human_target: developers running local LLMs on Apple Silicon
machine_target: AI assistants helping the above developers
---

# MoA Hybrid Template

**Drop-in template for running Hermes MoA (Mixture-of-Agents) with a local 4bit LLM as advisor + a cloud model as aggregator. n=20 validated. ~10 minutes from zero to working.**

---

## For AI Assistants

> If you're an AI assistant reading this to help a user set up Hermes MoA, here's the **one-screen summary**:
>
> 1. This is a **Hermes skill template** under `moa-bench-kit` not a standalone product
> 2. Three files matter: `SKILL.md` (install), `references/config-template.yaml` (config), `references/bench_moa_template.py` (validate)
> 3. **API keys are intentionally blank** (`<YOUR_*>` placeholders) — never commit real keys
> 4. The recommended preset is `conservative_500` (ref_max=500, saves ~9% time vs baseline)
> 5. Prerequisites: `~/.hermes/config.yaml` exists, oMLX running on `localhost:8000` (or change URL), a cloud API key
> 6. **Known gotchas** (from real runs): use `/Users/ct/.hermes/hermes-agent/venv/bin/python3` not bare `python3`; never use `bench_moa.swap_to()` directly (use `deep_merge_presets()` instead); oMLX needs `memory_guard_tier` set via settings.json then full app restart
> 7. If user asks "what is MoA / repo / git init", explain in plain words — this audience is beginner-friendly
> 8. The benchmark script returns JSON — pipe through `jq` if user wants formatted output
>
> Full validation data is in `references/worked-example.md`.

---

## Who this is for

You should use this template if **all** of these are true:

- ✅ You run Hermes Agent on macOS
- ✅ You have an Apple Silicon Mac with 32GB+ RAM
- ✅ You have oMLX (or compatible local OpenAI-compatible server) running
- ✅ You want to run a smaller model locally for "thinking" but a bigger model in the cloud for "final answer"
- ✅ You care about token cost (cloud model is only invoked as aggregator, not advisor)
- ✅ You are willing to run a 20-query smoke test to confirm your setup works

You **shouldn't** use this if:

- ❌ You don't have local inference set up (just use cloud-only MoA)
- ❌ You only have 16GB RAM (a 27B 4bit model needs ~14GB resident)
- ❌ Your cloud provider is the same as your local one (then MoA adds latency without saving tokens)
- ❌ You want one-shot answers with no validation step (this template enforces measurement)

---

## Quick start (5-minute path)

```bash
# 1. Copy config template into your Hermes config
cp references/config-template.yaml ~/.hermes/config.yaml.d/moa.yaml
$EDITOR ~/.hermes/config.yaml.d/moa.yaml   # fill in <YOUR_*> placeholders

# 2. Verify oMLX is up (or any local OpenAI-compatible server)
curl -s http://localhost:8000/v1/models | jq '.data[].id'

# 3. Smoke-test your MoA setup (takes ~5-15 minutes depending on hardware)
python3 references/bench_moja_template.py --queries 20
# expect: avg ~50s, p95 ~90s, errors=0

# 4. Use it
# In CLI: /moa "your question here"
# In Telegram: /moa your question here
```

If step 1 fails on the `models.providers.*.api_key` validation, see **§ Troubleshooting** in `SKILL.md`.

---

## How it works (one paragraph)

Hermes MoA runs **N "advisors" in parallel** on the same prompt (here, N=1: your local 4bit model), then sends their outputs to a **single aggregator** model (your cloud model), which produces the final answer. The advisor saves you cloud-token cost on every non-final call. The aggregator saves you local-GPU time on the final read/write step. With `conservative_500`, advisor outputs are capped at 500 tokens, which empirically gives ~9% latency win without quality loss (validated on n=20; see `references/worked-example.md`).

This is the standard "Mixture of Agents" pattern — see the original paper: [Together AI, 2024](https://arxiv.org/abs/2406.04692). Our contribution is the **specifically-tuned hybrid local/cloud pairing** for Apple Silicon Mac minis.

---

## What's in this repo

| File | For whom | What it does |
|---|---|---|
| `SKILL.md` | Both | Install + troubleshooting guide (read this first) |
| `README.md` | Both | This file (overview + quick start) |
| `references/config-template.yaml` | Human | Sample config block, all API keys as `<YOUR_*>` placeholders |
| `references/bench_moja_template.py` | Human + AI | n=20 bench script — pipe through `jq` for JSON output |
| `references/worked-example.md` | Both | Full 2026-07-18 production run data + analysis |

---

## Validated benchmark results

| Preset | `reference_max_tokens` | avg | p95 | errors | vs baseline |
|---|---|---|---|---|---|
| `user_turn_800` | 800 | 60.0s | 100.0s | 0 | baseline |
| **`conservative_500`** | **500** | **54.6s** | **90.8s** | **0** | **-9.0%** |

n=20 validation: avg=47.4s, median=51.4s, p95=91.2s, errs=0. Full breakdown in `references/worked-example.md`.

**Interpretation:**
- `ref_max` is the per-advisor-output token cap. Higher = longer/worse per-call cost; lower = more concise but possibly truncated reasoning.
- `800` is the default — we discovered `500` is sufficient for most reasoning tasks without quality regression.
- This is **not** a max-quality benchmark, it's a "did anything regress" smoke test. For quality measurement, see the working-example.

---

## Requirements

You need to bring these yourself (we don't redistribute them):

| Requirement | Why |
|---|---|
| Apple Silicon Mac with 32GB+ RAM | 27B 4bit needs ~14GB resident + ~2GB KV cache headroom |
| oMLX local inference server | We use it because it has OpenAI-compatible API + remote Mac access |
| A 27B-class 4bit MLX-format model | We tested with `Qwopus3.6-27B-v2-MLX-4bit`; any 27B/30B-A3B should work |
| A cloud OpenAI-compatible API key | We used MiniMax; any provider with chat-completions API works |
| Hermes Agent installed | The MoA runtime lives inside Hermes |

Tested on: **Mac mini M4 10C 32GB**, macOS 26.5.1, oMLX v0.x, Hermes Agent current.

---

## Limitations / honest disclosures

1. **No fine-tuned evaluation.** `conservative_500` wins on latency, but we did *not* run an A/B quality study. If you have a use case where reasoning depth matters more than speed, use `user_turn_800`.
2. **Single-advisor only.** This template uses N=1 advisor. The original MoA paper uses N≥3. Adding more advisors increases cloud cost linearly — we decided that's not worth it for a 4bit local advisor.
3. **Hardware-specific.** We tested on Mac mini M4 only. Other M-series Macs should work but we have no data on Intel/AMD/Linux behavior.
4. **Cloud cost is real.** Even with local advisor, you still pay for the aggregator call. If your cloud model is the same size as your local one, MoA adds latency without saving cost.
5. **No automatic failover.** If oMLX is down, MoA falls back to cloud-only — gracefully, but you lose the cost-saving benefit.

---

## License

MIT. Use freely. **Do not** commit your filled-in `config.yaml` with real API keys to public repos — `.gitignore` already excludes it, but please double-check before pushing.

---

## Credits

- Hermes MoA runtime (Nous Research)
- oMLX local inference (Nous Research)
- MoA paper: [Together AI, 2024](https://arxiv.org/abs/2406.04692)
- Validation run: 2026-07-18 (hardware + data in `worked-example.md`)
