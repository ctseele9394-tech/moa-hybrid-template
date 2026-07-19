# MoA Hybrid Template

**Drop-in template for running Hermes MoA (Mixture-of-Agents) with a local 4bit LLM as advisor + a cloud model as aggregator.**

## What this is

A pre-tuned MoA configuration + bench script + setup guide that you can adapt to your own hardware. Originally validated on a Mac mini M4 10C 32GB with a 27B 4bit local model + a cloud aggregator model.

## Quick start

1. **Read** [`SKILL.md`](./SKILL.md) for the full installation guide
2. **Copy** [`references/config-template.yaml`](./references/config-template.yaml) to your `~/.hermes/config.yaml`, replace `<YOUR_*>` placeholders with your own values
3. **Verify** by running `references/bench_moa_template.py` (n=20 query smoke test)
4. **Use** `/moa <your question>` in Telegram or CLI

## What's in here

| File | Purpose |
|---|---|
| `SKILL.md` | Full installation + troubleshooting guide |
| `references/config-template.yaml` | Sample config (API keys left blank — fill in your own) |
| `references/bench_moa_template.py` | n=20 bench script to validate your setup |
| `references/worked-example.md` | Real numbers from the 2026-07-18 production validation |

## Requirements

You need to provide:

- **Mac mini M-series** (or any Apple Silicon with 32GB+ RAM)
- **oMLX** local inference server (Nous Research)
- **A 27B-class 4bit model** in MLX format
- **A cloud provider account** (OpenAI-compatible API)
- **Hermes Agent** with MoA runtime enabled

## Validated benchmark results

| Preset | `reference_max_tokens` | avg | p95 | errors | vs baseline |
|---|---|---|---|---|---|
| `user_turn_800` | 800 | 60.0s | 100.0s | 0 | baseline |
| `conservative_500` | **500** | **54.6s** | **90.8s** | **0** | **-9.0%** |

n=20 validation: avg=47.4s, median=51.4s, p95=91.2s, errs=0. See `references/worked-example.md` for the full breakdown.

## License

MIT. Use freely. **Do not** commit your filled-in `config.yaml` with real API keys to public repos — the `.gitignore` already excludes it, but please double-check before pushing.

## Credits

- Hermes MoA runtime
- oMLX by Nous Research
- MoA paper: [Together AI, 2024](https://arxiv.org/abs/2406.04692)
- Validation data: 2026-07-18 production run
