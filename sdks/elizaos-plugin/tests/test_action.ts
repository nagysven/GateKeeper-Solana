import assert from "node:assert";
import { evaluateIntentAction } from "../dist/index.js";
import type { IAgentRuntime, Memory, State } from "../dist/index.js";

// Save original global fetch
const originalFetch = globalThis.fetch;

async function runTests() {
  console.log("=================================================");
  console.log("🧪 Running ElizaOS Gatekeeper Plugin Smoke Tests");
  console.log("=================================================");

  const mockRuntime: IAgentRuntime = {
    getSetting: (key: string) => {
      if (key === "GATEKEEPER_API_KEY") return "gk_test_mock_key";
      if (key === "GATEKEEPER_API_URL") return "https://gk.ai-futures-bot.pro/api/v1/intent/evaluate";
      return undefined;
    },
  };

  // -------------------------------------------------------------
  // Test 1: Action Validation Filter
  // -------------------------------------------------------------
  console.log("\n[Test 1] Validating action keyword matching...");
  const validMsg: Memory = { content: { text: "Can you swap 0.5 SOL for USDC?" } };
  const invalidMsg: Memory = { content: { text: "What is the weather today?" } };

  const isValid = await evaluateIntentAction.validate(mockRuntime, validMsg);
  const isInvalid = await evaluateIntentAction.validate(mockRuntime, invalidMsg);

  assert.strictEqual(isValid, true, "Should validate messages mentioning swap/trade");
  assert.strictEqual(isInvalid, false, "Should reject messages without trading context");
  console.log("  ✓ Validation logic passed.");

  // -------------------------------------------------------------
  // Test 2: Case A - Successful 'APPROVED' Intent Dispatch
  // -------------------------------------------------------------
  console.log("\n[Test 2] Case A: Evaluating APPROVED Pre-Flight Swap...");
  const mockApprovedPayload = {
    intent_id: "intent-test-approved-123",
    decision: "APPROVED",
    action: "DISPATCH",
    simulated_compute_units: 42000,
    clamped_compute_units: 47040,
    execution_time_ms: 71.5,
    selected_route: "RAYDIUM",
    estimated_hops: 1,
    clamped_cu_saved: 152960,
    fees_saved_lamports: 0,
    rejection_reason: null,
    rejection_details: null,
    candidates_evaluated: 2,
  };

  globalThis.fetch = async (input: RequestInfo | URL, init?: RequestInit) => {
    return new Response(JSON.stringify(mockApprovedPayload), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  };

  let approvedCallbackCalled = false;
  let approvedCallbackData: any = null;

  const callbackA = async (resp: any) => {
    approvedCallbackCalled = true;
    approvedCallbackData = resp;
  };

  const tradeStateA: State = {
    tokenIn: "So11111111111111111111111111111111111111112",
    tokenOut: "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
    amountIn: 100_000_000,
    maxSlippageBps: 50,
  };

  const resultA = await evaluateIntentAction.handler(
    mockRuntime,
    validMsg,
    tradeStateA,
    null,
    callbackA
  );

  assert.strictEqual(resultA, true, "Handler should return true when Gatekeeper approves swap");
  assert.strictEqual(approvedCallbackCalled, true, "Callback must be invoked on approval");
  assert.strictEqual(approvedCallbackData.action, "GATEKEEPER_APPROVED");
  assert.ok(
    approvedCallbackData.text.includes("APPROVED in 71.5ms"),
    "Message text must detail approval latency"
  );
  assert.ok(
    approvedCallbackData.text.includes("47040"),
    "Message text must include clamped compute unit limit"
  );
  console.log("  ✓ Case A passed: Handler returned TRUE, callback fired with APPROVED status.");

  // -------------------------------------------------------------
  // Test 3: Case B - Slippage / Revert 'HARD_ABORT' Intercept
  // -------------------------------------------------------------
  console.log("\n[Test 3] Case B: Evaluating HARD_ABORT (0x1771 Revert Intercept)...");
  const mockRevertedPayload = {
    intent_id: "intent-test-rejected-999",
    decision: "REJECTED",
    action: "HARD_ABORT",
    simulated_compute_units: 0,
    clamped_compute_units: 0,
    execution_time_ms: 54.2,
    selected_route: null,
    estimated_hops: 1,
    clamped_cu_saved: 0,
    fees_saved_lamports: 7556,
    rejection_reason: "ERR_SLIPPAGE_EXCEEDED",
    rejection_details: "Slippage tolerance exceeded (0x1771)",
    candidates_evaluated: 2,
  };

  globalThis.fetch = async (input: RequestInfo | URL, init?: RequestInit) => {
    return new Response(JSON.stringify(mockRevertedPayload), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  };

  let rejectedCallbackCalled = false;
  let rejectedCallbackData: any = null;

  const callbackB = async (resp: any) => {
    rejectedCallbackCalled = true;
    rejectedCallbackData = resp;
  };

  const tradeStateB: State = {
    tokenIn: "So11111111111111111111111111111111111111112",
    tokenOut: "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
    amountIn: 1_000_000_000,
    maxSlippageBps: 1, // Impossibly tight slippage
  };

  const resultB = await evaluateIntentAction.handler(
    mockRuntime,
    validMsg,
    tradeStateB,
    null,
    callbackB
  );

  assert.strictEqual(resultB, false, "Handler should return false when Gatekeeper triggers HARD_ABORT");
  assert.strictEqual(rejectedCallbackCalled, true, "Callback must be invoked on rejection");
  assert.strictEqual(rejectedCallbackData.action, "GATEKEEPER_REJECTED");
  assert.ok(
    rejectedCallbackData.text.includes("HARD_ABORT"),
    "Message text must indicate HARD_ABORT"
  );
  assert.ok(
    rejectedCallbackData.text.includes("0 Lamports (0.00 SOL verbrannt)"),
    "Message text must guarantee zero gas burned"
  );
  assert.ok(
    rejectedCallbackData.text.includes("ERR_SLIPPAGE_EXCEEDED"),
    "Message text must include deterministic abort reason"
  );
  console.log("  ✓ Case B passed: Handler returned FALSE, callback fired with HARD_ABORT status.");

  // Restore fetch
  globalThis.fetch = originalFetch;

  console.log("\n=================================================");
  console.log("✅ ALL ELIZAOS PLUGIN TESTS PASSED SUCCESSFULLY!");
  console.log("=================================================\n");
}

runTests().catch((err) => {
  console.error("\n❌ TEST FAILED:", err);
  process.exit(1);
});
