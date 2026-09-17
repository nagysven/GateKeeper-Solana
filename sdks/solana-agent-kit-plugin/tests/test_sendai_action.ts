import assert from "node:assert";
import {
  createGatekeeperPreflightAction,
  GatekeeperPreflightInputSchema,
} from "../dist/index.js";

// Save original global fetch
const originalFetch = globalThis.fetch;

async function runTests() {
  console.log("==================================================================");
  console.log("🧪 Running Solana Agent Kit (SendAI) Gatekeeper Unit & Smoke Tests");
  console.log("==================================================================");

  const action = createGatekeeperPreflightAction({
    apiKey: "gk_test_sendai_mock",
    baseUrl: "https://gk.ai-futures-bot.pro",
  });

  // Verify action properties
  assert.strictEqual(
    action.name,
    "gatekeeper_preflight_check",
    "Action name must be gatekeeper_preflight_check"
  );

  // -------------------------------------------------------------
  // Test 1: Zod Input Schema Validation
  // -------------------------------------------------------------
  console.log("\n[Test 1] Validating Zod Input Schema (Input-Mint, Output-Mint, Amount, Max-Slippage)...");
  const validPayload = {
    inputMint: "So11111111111111111111111111111111111111112",
    outputMint: "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
    amount: 100_000_000,
    maxSlippageBps: 50,
  };
  const parsed = GatekeeperPreflightInputSchema.safeParse(validPayload);
  assert.strictEqual(parsed.success, true, "Valid input must pass Zod schema parsing");

  const invalidPayload = {
    inputMint: "So11111111111111111111111111111111111111112",
    // Missing required outputMint and amount
  };
  const parsedInvalid = GatekeeperPreflightInputSchema.safeParse(invalidPayload);
  assert.strictEqual(parsedInvalid.success, false, "Malformed input must be rejected by Zod");
  console.log("  ✓ Zod schema validation passed.");

  // -------------------------------------------------------------
  // Test 2: Testfall 1 - Approval-Pfad mit optimierten Parametern
  // -------------------------------------------------------------
  console.log("\n[Test 2] Testfall 1: Approval-Pfad (Status 'APPROVED' & optimiertes Compute-Budget)...");
  const mockApprovedResponse = {
    intent_id: "intent-sendai-approved-101",
    decision: "APPROVED",
    action: "DISPATCH",
    simulated_compute_units: 42500,
    clamped_compute_units: 49078,
    execution_time_ms: 68.4,
    selected_route: "RAYDIUM_CLMM",
    estimated_hops: 1,
    clamped_cu_saved: 150922,
    fees_saved_lamports: 0,
    rejection_reason: null,
    rejection_details: null,
    candidates_evaluated: 2,
  };

  globalThis.fetch = async () => {
    return new Response(JSON.stringify(mockApprovedResponse), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  };

  const resultApproval = await action.handler(null, validPayload);

  assert.strictEqual(resultApproval.status, "APPROVED", "Status must be 'APPROVED'");
  assert.strictEqual(resultApproval.decision, "APPROVED");
  assert.strictEqual(resultApproval.action, "DISPATCH");
  assert.strictEqual(resultApproval.clampedComputeUnits, 49078, "Must return clamped compute units");
  assert.strictEqual(resultApproval.clampedCuSaved, 150922, "Must return saved compute units");
  assert.strictEqual(resultApproval.selectedRoute, "RAYDIUM_CLMM");
  assert.strictEqual(resultApproval.gasPaidOnChain, 0);
  assert.ok(
    resultApproval.message.includes("Gatekeeper Pre-Flight APPROVED"),
    "Message must state preflight approved"
  );
  console.log("  ✓ Testfall 1 passed: Status 'APPROVED', 49,078 clamped CU limit, 150,922 CU saved.");

  // -------------------------------------------------------------
  // Test 3: Testfall 2 - Revert-Intercept (0x1771 Slippage) mit Abbruch & Budget-Schonung
  // -------------------------------------------------------------
  console.log("\n[Test 3] Testfall 2: Revert-Intercept (Status 'HARD_ABORT' & 0 Gas Burned)...");
  const mockRevertedResponse = {
    intent_id: "intent-sendai-reverted-902",
    decision: "REJECTED",
    action: "HARD_ABORT",
    simulated_compute_units: 0,
    clamped_compute_units: 0,
    execution_time_ms: 48.9,
    selected_route: null,
    estimated_hops: 1,
    clamped_cu_saved: 0,
    fees_saved_lamports: 7556,
    rejection_reason: "ERR_SLIPPAGE_EXCEEDED",
    rejection_details: "Slippage tolerance exceeded: required 0.85%, allowed 0.01% (0x1771)",
    candidates_evaluated: 2,
  };

  globalThis.fetch = async () => {
    return new Response(JSON.stringify(mockRevertedResponse), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  };

  const tightSlippagePayload = {
    ...validPayload,
    maxSlippageBps: 1, // 0.01%
  };

  const resultAbort = await action.handler(null, tightSlippagePayload);

  assert.strictEqual(resultAbort.status, "HARD_ABORT", "Status must be 'HARD_ABORT'");
  assert.strictEqual(resultAbort.decision, "REJECTED");
  assert.strictEqual(resultAbort.action, "HARD_ABORT");
  assert.strictEqual(resultAbort.gasPaidOnChain, 0, "Guaranteed 0 gas burned on-chain");
  assert.strictEqual(resultAbort.feesSavedLamports, 7556, "Fees saved must match 7556 Lamports");
  assert.strictEqual(resultAbort.rejectionReason, "ERR_SLIPPAGE_EXCEEDED");
  assert.ok(
    resultAbort.message.includes("HARD_ABORT"),
    "Message must state HARD_ABORT triggered"
  );
  assert.ok(
    resultAbort.message.includes("0 gas burned on-chain"),
    "Message must confirm 0 gas burned"
  );
  console.log("  ✓ Testfall 2 passed: Status 'HARD_ABORT', 0 gas burned on-chain, 7,556 Lamports preserved.");

  // Restore fetch
  globalThis.fetch = originalFetch;

  console.log("\n==================================================================");
  console.log("✅ ALL SOLANA AGENT KIT (SENDAI) SMOKE TESTS PASSED (EXIT CODE 0)!");
  console.log("==================================================================\n");
}

runTests().catch((err) => {
  console.error("\n❌ SMOKE TEST FAILED:", err);
  process.exit(1);
});
