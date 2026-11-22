#!/usr/bin/env python3
"""GateKeeper Solana Pre-Flight Validation Helper for AI Agents.

Uses standard library only (no 3rd-party dependencies required).
Simulates swap intents against the GateKeeper gateway before signing.
"""

import argparse
import json
import sys
import urllib.error
import urllib.request

DEFAULT_GATEWAY_URL = "https://gk.ai-futures-bot.pro/api/v1/preflight"


def run_preflight(
    token_in: str,
    token_out: str,
    amount_in: int,
    max_slippage_bps: int = 50,
    api_key: str = "gk_live_demo",
    gateway_url: str = DEFAULT_GATEWAY_URL,
) -> dict:
    payload = {
        "token_in": token_in,
        "token_out": token_out,
        "amount_in": amount_in,
        "max_slippage_bps": max_slippage_bps,
    }
    data = json.dumps(payload).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "X-Gatekeeper-Key": api_key,
        "User-Agent": "GateKeeper-Agensi-Skill/1.0",
    }

    req = urllib.request.Request(gateway_url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=10.0) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8")
        try:
            err_json = json.loads(body)
            return {"status": "ERROR", "error": err_json.get("detail", body), "is_approved": False}
        except Exception:
            return {"status": "ERROR", "error": f"HTTP {e.code}: {body}", "is_approved": False}
    except Exception as e:
        return {"status": "ERROR", "error": str(e), "is_approved": False}


def main():
    parser = argparse.ArgumentParser(description="GateKeeper Pre-Flight Swap Checker for AI Agents")
    parser.add_argument("--input-mint", required=True, help="Input token mint address (e.g. SOL)")
    parser.add_argument("--output-mint", required=True, help="Output token mint address (e.g. USDC)")
    parser.add_argument("--amount", type=int, required=True, help="Amount in base units / lamports")
    parser.add_argument("--max-slippage-bps", type=int, default=50, help="Max slippage in basis points (default: 50)")
    parser.add_argument("--api-key", default="gk_live_demo", help="GateKeeper API key")
    parser.add_argument("--gateway-url", default=DEFAULT_GATEWAY_URL, help="Custom gateway URL")

    args = parser.parse_args()

    result = run_preflight(
        token_in=args.input_mint,
        token_out=args.output_mint,
        amount_in=args.amount,
        max_slippage_bps=args.max_slippage_bps,
        api_key=args.api_key,
        gateway_url=args.gateway_url,
    )

    print(json.dumps(result, indent=2))
    if not result.get("is_approved", True):
        sys.exit(1)


if __name__ == "__main__":
    main()
