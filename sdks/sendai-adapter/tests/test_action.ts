import assert from "node:assert";
import {
  createGatekeeperPreflightAction,
  GatekeeperPreflightInputSchema,
} from "../dist/index.js";

// Save original global fetch
const originalFetch = globalThis.fetch;

async function runTests() {
  console.log("==========================================================");
  console.log("🧪 Running Solana Agent Kit (SendAI) Gatekeeper Unit Tests");
  console.log("==========================================================");

  const action = createGatekeeperPreflightAction({
    apiKey: "gk_test_mock_key",
    baseUrl: "https://gk.ai-futures-bot.pro",
  });

  // -------------------------------------------------------------
  // Test 1: Zod Schema Validation
  // -------------------------------------------------------------
  console.log("\n[Test 1] Validating Zod Input Schema...");
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
    // Missing outputMint and amount
  };
  const parsedInvalid = GatekeeperPreflightInputSchema.safeParse(invalidPayload);
  assert.strictEqual(parsedInvalid.success, false, "Malformed input must be rejected by Zod");
  console.log("  ✓ Zod schema validation passed.");

  // -------------------------------------------------------------
  // Test 2: Case A - Successful 'APPROVED' Intent Dispatch
  // -------------------------------------------------------------
  console.log("\n[Test 2] Case A: Evaluating APPROVED Pre-Flight Swap...");
  const mockApprovedPayload = {
    intent_id: "intent-sendai-approved-123",
    decision: "APPROVED",
    action: "DISPATCH",
    simulated_compute_units: 43820,
    clamped_compute_units: 49078,
    execution_time_ms: 76.2,
    selected_route: "RAYDIUM",
    estimated_hops: 1,
    clamped_cu_saved: 150922,
    fees_saved_lamports: 0,
    rejection_reason: null,
    rejection_details: null,
    candidates_evaluated: 2,
  };

  globalThis.fetch = async () => {
    return new Response(JSON.stringify(mockApprovedPayload), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  };

  const resultA = await action.handler(null, validPayload);

  assert.strictEqual(resultA.success, true, "Handler must return success: true for approved trade");
  assert.strictEqual(resultA.decision, "APPROVED");
  assert.strictEqual(resultA.action, "DISPATCH");
  assert.strictEqual(resultA.clampedComputeUnits, 49078);
  assert.strictEqual(resultA.clampedCuSaved, 150922);
  assert.ok(resultA.message.includes("APPROVED in 76.2ms"));
  console.log("  ✓ Case A passed: Intent APPROVED with 49,078 clamped CU limit.");

  // -------------------------------------------------------------
  // Test 3: Case B - Slippage / Revert 'HARD_ABORT' Intercept
  // -------------------------------------------------------------
  console.log("\n[Test 3] Case B: Evaluating HARD_ABORT (0x1771 Revert Intercept)...");
  const mockRevertedPayload = {
    intent_id: "intent-sendai-rejected-999",
    decision: "REJECTED",
    action: "HARD_ABORT",
    simulated_compute_units: 0,
    clamped_compute_units: 0,
    execution_time_ms: 55.4,
    selected_route: null,
    estimated_hops: 1,
    clamped_cu_saved: 0,
    fees_saved_lamports: 7556,
    rejection_reason: "ERR_SLIPPAGE_EXCEEDED",
    rejection_details: "Slippage tolerance exceeded (0x1771)",
    candidates_evaluated: 2,
  };

  globalThis.fetch = async () => {
    return new Response(JSON.stringify(mockRevertedPayload), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  };

  const tightSlippagePayload = {
    ...validPayload,
    maxSlippageBps: 1,
  };

  const resultB = await action.handler(null, tightSlippagePayload);

  assert.strictEqual(resultB.success, false, "Handler must return success: false on HARD_ABORT");
  assert.strictEqual(resultB.decision, "REJECTED");
  assert.strictEqual(resultB.action, "HARD_ABORT");
  assert.strictEqual(resultB.gasPaidOnChain, 0, "Guaranteed 0 gas paid on-chain");
  assert.strictEqual(resultB.feesSavedLamports, 7556);
  assert.strictEqual(resultB.rejectionReason, "ERR_SLIPPAGE_EXCEEDED");
  assert.ok(resultB.message.includes("0 gas burned on-chain"));
  console.log("  ✓ Case B passed: Revert intercepted, 0 gas burned, 7,556 lamports saved.");

  // Restore fetch
  globalThis.fetch = originalFetch;

  console.log("\n==========================================================");
  console.log("✅ ALL SOLANA AGENT KIT (SENDAI) TESTS PASSED SUCCESSFULLY!");
  console.log("==========================================================\n");
}

runTests().catch((err) => {
  console.error("\n❌ TEST FAILED:", err);
  process.exit(1);
});
