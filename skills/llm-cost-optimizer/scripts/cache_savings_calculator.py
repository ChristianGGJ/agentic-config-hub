#!/usr/bin/env python3
"""Estimate LLM API cost under prompt caching and Batch APIs for a repeated-prefix workload.

Deterministic back-of-envelope calculator for the llm-cost-optimizer skill. No network
and no LLM calls -- pure arithmetic on token counts and prices.

Prices are per 1,000,000 tokens and may be absolute dollars OR relative units; the
cache/batch multipliers below are far more stable than any absolute price, so the
comparison holds either way. Multipliers are relative to the base input price and should
be re-verified against current provider docs:

  cache read         ~0.10x input
  cache write   5m   ~1.25x input
  cache write   1h   ~2.00x input
  batch API          ~0.50x input AND output

The model treats all `requests` as landing inside one TTL window (or kept warm by
re-warming); a prefix shorter than --min-cacheable-tokens will not engage caching.

Use --realtime-only for latency-bound workloads that cannot use the (async) Batch API;
the recommendation is then chosen from the real-time options only.

Exit codes:
  0  an applicable lever beats the uncached real-time baseline (savings available)
  1  no applicable lever beats the uncached real-time baseline
  2  invalid arguments
"""
import argparse
import json
import math
import sys

READ_MULT = 0.10
WRITE_MULT = {"5m": 1.25, "1h": 2.00}
BATCH_MULT = 0.50


def compute(stable, volatile, output, requests, input_price, output_price, ttl, min_cacheable,
            realtime_only=False):
    inp = input_price / 1_000_000.0
    outp = output_price / 1_000_000.0
    write_mult = WRITE_MULT[ttl]

    per_req_recurring = volatile * inp + output * outp

    uncached = requests * ((stable + volatile) * inp + output * outp)

    cacheable = stable >= min_cacheable
    if cacheable:
        cached_stable = (
            stable * inp * write_mult
            + max(0, requests - 1) * stable * inp * READ_MULT
        )
        cached = cached_stable + requests * per_req_recurring
    else:
        # Prefix below the model minimum: the breakpoint silently never caches.
        cached = uncached

    batched = uncached * BATCH_MULT
    batched_cached = cached * BATCH_MULT

    options = {
        "uncached_realtime": uncached,
        "cached_realtime": cached,
        "batched": batched,
        "batched_and_cached": batched_cached,
    }
    if realtime_only:
        eligible = ("uncached_realtime", "cached_realtime")
    else:
        eligible = tuple(options.keys())
    best_name = min(eligible, key=lambda k: options[k])
    best_cost = options[best_name]
    savings = uncached - best_cost
    savings_pct = (savings / uncached * 100.0) if uncached > 0 else 0.0

    # Smallest reuse count at which caching the stable prefix beats not caching it.
    break_even = math.floor((write_mult - READ_MULT) / (1.0 - READ_MULT)) + 1

    return {
        "inputs": {
            "stable_tokens": stable,
            "volatile_tokens": volatile,
            "output_tokens": output,
            "requests": requests,
            "input_price_per_mtok": input_price,
            "output_price_per_mtok": output_price,
            "ttl": ttl,
            "min_cacheable_tokens": min_cacheable,
            "realtime_only": realtime_only,
        },
        "prefix_is_cacheable": cacheable,
        "cache_break_even_requests": break_even,
        "cost": {k: round(v, 6) for k, v in options.items()},
        "recommended": best_name,
        "recommended_cost": round(best_cost, 6),
        "savings_vs_uncached": round(savings, 6),
        "savings_pct_vs_uncached": round(savings_pct, 2),
    }


def render_text(result):
    inputs = result["inputs"]
    lines = []
    lines.append("LLM cost estimate (prices per 1,000,000 tokens; multipliers verify against current docs)")
    lines.append("=" * 84)
    lines.append(
        "workload: {req} request(s) x [{s} stable + {v} volatile in, {o} out] tokens".format(
            req=inputs["requests"],
            s=inputs["stable_tokens"],
            v=inputs["volatile_tokens"],
            o=inputs["output_tokens"],
        )
    )
    lines.append(
        "prices:   {ip} in / {op} out per MTok    TTL: {ttl}    min-cacheable: {mc} tokens".format(
            ip=inputs["input_price_per_mtok"],
            op=inputs["output_price_per_mtok"],
            ttl=inputs["ttl"],
            mc=inputs["min_cacheable_tokens"],
        )
    )
    lines.append("")
    if not result["prefix_is_cacheable"]:
        lines.append(
            "NOTE: stable prefix ({s} tokens) is below the {mc}-token minimum -- it will NOT cache.".format(
                s=inputs["stable_tokens"], mc=inputs["min_cacheable_tokens"]
            )
        )
        lines.append("")
    lines.append("cache break-even: caching the prefix pays off from reuse #{be} onward.".format(
        be=result["cache_break_even_requests"]
    ))
    lines.append("")
    lines.append("{:<24} {:>16}".format("option", "cost"))
    lines.append("-" * 41)
    labels = {
        "uncached_realtime": "uncached (real-time)",
        "cached_realtime": "cached (real-time)",
        "batched": "batched (async)",
        "batched_and_cached": "batched + cached",
    }
    realtime_only = inputs.get("realtime_only", False)
    for key in ("uncached_realtime", "cached_realtime", "batched", "batched_and_cached"):
        note = ""
        if key == result["recommended"]:
            note = "  <== recommended"
        elif realtime_only and key in ("batched", "batched_and_cached"):
            note = "  (excluded: --realtime-only)"
        lines.append("{:<24} {:>16.6f}{}".format(labels[key], result["cost"][key], note))
    lines.append("")
    lines.append(
        "best: {name}  (saves {sav:.6f}, {pct:.2f}% vs uncached real-time)".format(
            name=labels[result["recommended"]],
            sav=result["savings_vs_uncached"],
            pct=result["savings_pct_vs_uncached"],
        )
    )
    return "\n".join(lines)


def build_parser():
    p = argparse.ArgumentParser(
        description="Estimate LLM cost under prompt caching and Batch APIs for a repeated-prefix workload.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--stable-tokens", type=int, required=True,
                   help="cacheable prefix tokens reused across requests (system prompt, tools, static context)")
    p.add_argument("--volatile-tokens", type=int, default=0,
                   help="uncacheable input tokens per request (the varying user turn); default 0")
    p.add_argument("--output-tokens", type=int, default=0,
                   help="output tokens per request; default 0")
    p.add_argument("--requests", type=int, required=True,
                   help="number of requests reusing the prefix within the TTL window")
    p.add_argument("--input-price", type=float, default=1.0,
                   help="price per 1,000,000 input tokens (absolute or relative); default 1.0")
    p.add_argument("--output-price", type=float, default=None,
                   help="price per 1,000,000 output tokens; default 5x input-price")
    p.add_argument("--ttl", choices=("5m", "1h"), default="5m",
                   help="cache TTL: 5m (write ~1.25x) or 1h (write ~2x); default 5m")
    p.add_argument("--min-cacheable-tokens", type=int, default=1024,
                   help="model minimum cacheable prefix; ~4096 for Opus-tier, ~1024-2048 elsewhere; default 1024")
    p.add_argument("--realtime-only", action="store_true",
                   help="workload needs synchronous responses; exclude the async Batch API options")
    p.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    return p


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.output_price is None:
        args.output_price = args.input_price * 5.0

    errors = []
    if args.stable_tokens < 0:
        errors.append("--stable-tokens must be >= 0")
    if args.volatile_tokens < 0:
        errors.append("--volatile-tokens must be >= 0")
    if args.output_tokens < 0:
        errors.append("--output-tokens must be >= 0")
    if args.requests < 1:
        errors.append("--requests must be >= 1")
    if args.input_price < 0 or args.output_price < 0:
        errors.append("prices must be >= 0")
    if args.min_cacheable_tokens < 0:
        errors.append("--min-cacheable-tokens must be >= 0")
    if errors:
        for e in errors:
            sys.stderr.write("error: {}\n".format(e))
        return 2

    result = compute(
        stable=args.stable_tokens,
        volatile=args.volatile_tokens,
        output=args.output_tokens,
        requests=args.requests,
        input_price=args.input_price,
        output_price=args.output_price,
        ttl=args.ttl,
        min_cacheable=args.min_cacheable_tokens,
        realtime_only=args.realtime_only,
    )

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(render_text(result))

    return 0 if result["recommended"] != "uncached_realtime" else 1


if __name__ == "__main__":
    sys.exit(main())
