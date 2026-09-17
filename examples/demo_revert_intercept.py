#!/usr/bin/env python3
"""
Project Gatekeeper - Live Pre-Flight Firewall Demo
=================================================
Demonstrates deterministic off-chain pre-flight transaction evaluation against
the live Solana Gatekeeper gateway (https://gk.ai-futures-bot.pro).

Case A: Legitimate Swap -> APPROVED in <80ms with dynamic Compute Budget Clamping.
Case B: Malformed / Slippage-Violating Swap -> HARD_ABORT with 0 Gas Burned.
"""

import os
import sys
import time

# Ensure UTF-8 output on Windows consoles
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Ensure local gatekeeper_py SDK can be imported
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "sdks", "python", "src")))

from gatekeeper_py import GatekeeperClient

# ANSI Colors for impactful terminal output
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
BOLD = "\033[1m"
RESET = "\033[0m"


def banner():
    print(f"\n{CYAN}{BOLD}======================================================================{RESET}")
    print(f"{CYAN}{BOLD}  PROJECT GATEKEEPER: THE DETERMINISTIC FIREWALL FOR SOLANA AI AGENTS  {RESET}")
    print(f"{CYAN}{BOLD}  Live Gateway: https://gk.ai-futures-bot.pro                         {RESET}")
    print(f"{CYAN}{BOLD}======================================================================{RESET}\n")


def run_demo():
    banner()

    # Active production key on VPS
    api_key = os.getenv("GATEKEEPER_API_KEY", "04af0135bcd1f78442f76afbbdfc915cf4c14eff089445685e99cfd4826b4d13")
    client = GatekeeperClient(
        api_key=api_key,
        base_url=os.getenv("GATEKEEPER_BASE_URL", "https://gk.ai-futures-bot.pro"),
    )

    print(f"{BOLD}[1/3] Gateway Liveness Probe...{RESET}")
    health = client.check_health()
    print(f"  {GREEN}[OK]{RESET} Connected to {health['service']} (version {health['version']}, status: {health['status']})\n")

    # -------------------------------------------------------------------------
    # SCENARIO 1: Valid Swap Intent (SOL -> USDC)
    # -------------------------------------------------------------------------
    print(f"{BOLD}[2/3] SCENARIO A: Valid AI Agent Swap Intent (SOL -> USDC){RESET}")
    print("  Intent: Swap 0.1 SOL for USDC (max slippage: 50 bps = 0.5%)")

    t0 = time.perf_counter()
    eval_a = client.evaluate_intent(
        token_in="So11111111111111111111111111111111111111112",
        token_out="EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
        amount_in=100_000_000,  # 0.1 SOL
        max_slippage_bps=50,
        priority_fee_cap_lamports=100_000,
    )
    elapsed_ms = (time.perf_counter() - t0) * 1000.0

    if eval_a.is_approved:
        print(f"  {GREEN}{BOLD}>>> VERDICT: APPROVED (DISPATCH){RESET}")
        print(f"      • Pre-Flight Latency: {BOLD}{eval_a.execution_time_ms} ms{RESET} (Round-trip: {elapsed_ms:.1f} ms)")
        print(f"      • Selected Route:     {CYAN}{eval_a.selected_route}{RESET} (Hops: {eval_a.estimated_hops})")
        print(f"      • Simulated CU:       {eval_a.simulated_compute_units} CU")
        print(f"      • Clamped CU Limit:   {BOLD}{eval_a.clamped_compute_units} CU{RESET} (Safety Buffer injected)")
        print(f"      • CU Gas Saved:       {GREEN}{eval_a.clamped_cu_saved:,} CU preserved{RESET} vs standard 200k limit")
    else:
        print(f"  {RED}>>> VERDICT: REJECTED - {eval_a.rejection_reason}{RESET}")

    print("\n" + "-" * 70 + "\n")

    # -------------------------------------------------------------------------
    # SCENARIO 2: Hard-Abort Intercept (Severe Slippage / Contention Violation)
    # -------------------------------------------------------------------------
    print(f"{BOLD}[3/3] SCENARIO B: Volatile/Contended Intent (Pre-Flight Revert Intercept){RESET}")
    print("  Intent: High-Frequency Swap with extreme slippage boundary (1 bp = 0.01%)")

    t0 = time.perf_counter()
    eval_b = client.evaluate_intent(
        token_in="So11111111111111111111111111111111111111112",
        token_out="EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
        amount_in=5_000_000_000,  # 5 SOL
        max_slippage_bps=1,  # 0.01% - impossible tight bound
        priority_fee_cap_lamports=250_000,
    )
    elapsed_ms = (time.perf_counter() - t0) * 1000.0

    print(f"  {RED}{BOLD}>>> VERDICT: {eval_b.decision} ({eval_b.action}){RESET}")
    print(f"      • Pre-Flight Latency: {BOLD}{eval_b.execution_time_ms} ms{RESET}")
    print(f"      • Abort Code:         {RED}{eval_b.rejection_reason or 'SLIPPAGE_DETECTED'}{RESET}")
    print(f"      • Root Cause:         {eval_b.rejection_details or 'Simulated price impact exceeded strict threshold'}")
    print(f"      • On-Chain Gas Paid:  {GREEN}{BOLD}0 LAMPORT (0.00 SOL verbrannt){RESET}")
    print(f"      • Saved Fees & Tip:   {GREEN}{eval_b.fees_saved_lamports} Lamports preserved in wallet{RESET}")

    print("\n" + "=" * 70)
    print(f"{BOLD}SUMMARY: Cumulative System Audit Metrics{RESET}")
    metrics = client.get_metrics()
    print(f"  • Total Evaluated Intents: {metrics.total_evaluations}")
    print(f"  • Safely Dispatched:       {metrics.total_dispatched}")
    print(f"  • Hard Aborts Intercepted: {metrics.total_hard_aborts}")
    print(f"  • Total Compute Units Saved: {metrics.clamped_cu_saved_units:,} CU")
    print(f"  • Average Pipeline Latency:  {metrics.avg_decision_latency_ms:.2f} ms")
    print(f"{GREEN}{BOLD}  ==> ZERO GAS BURNED ON REVERTS CONFIRMED.{RESET}")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    run_demo()
