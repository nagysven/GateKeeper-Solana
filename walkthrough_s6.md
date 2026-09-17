# Walkthrough: Schritt 6 – Live Route Synthesis via DEX-Aggregator (Jupiter v6)

## Abgeschlossene Meilensteine

In Schritt 6 wurden die synthetischen Dummy-Routen durch echte Solana DEX-Routensynthese über die **Jupiter v6 Swap API** ersetzt:

---

### 1. Jupiter v6 Client ([`src/gatekeeper/engine/jupiter_client.py`](file:///f:/GateKeeper/src/gatekeeper/engine/jupiter_client.py))
- **`get_quote()`**:
  - Fragt den Jupiter Quote-Endpunkt (`/quote`) asynchron ab.
  - Unterstützt `onlyDirectRoutes=true` (Route A: Direkter Swap) und `onlyDirectRoutes=false` (Route B: Multi-Hop / Split / Optimaler Yield).
- **`get_swap_transaction()`**:
  - Ruft `/swap` ab und liefert die ungesignte Base64-VersionedTransaction (`swapTransaction`).
  - Setzt `dynamicComputeUnitLimit: false` (da Gatekeeper das dynamische Clamping übernimmt) und `prioritizationFeeLamports: 0`.
- Fehlerbehandlung über `JupiterApiError`.

---

### 2. Candidate Generator ([`src/gatekeeper/engine/candidate_generator.py`](file:///f:/GateKeeper/src/gatekeeper/engine/candidate_generator.py))
- Führt eine zweistufige parallele Erzeugung über `asyncio.gather` aus:
  1. Paralleler Abruf von Direct- und Multi-Hop-Quotes.
  2. Paralleler Abruf der zugehörigen ungesignten VersionedTransactions.
- **Automatisches Tagging**:
  - Route A (Direct): `estimated_hops = 1`, `is_split = False`, Clamping-Puffer $+12\%$.
  - Route B (Multi-Hop): `estimated_hops = len(routePlan)`, `is_split = True`, Clamping-Puffer $+20\%$.
  - DEX-Erkennung anhand der AMM-Labels (Raydium, Orca Whirlpool, Meteora).
- **Resilienter Fallback**: Bei API-Ausfällen oder Rate-Limits greift automatisch `fallback_to_synthetic`, sodass Gatekeeper auch bei Aggregator-Störungen stabil bleibt.

---

### 3. API-Integration ([`src/gatekeeper/api/v1/intents.py`](file:///f:/GateKeeper/src/gatekeeper/api/v1/intents.py))
- Wenn Clients keine expliziten Routen-Kandidaten an `/api/v1/intent/evaluate` übergeben, ruft Gatekeeper autonom den `RouteCandidateGenerator` auf, synthetisiert echte On-Chain-Routen und leitet diese an die Pre-Flight Simulation weiter.

---

### 4. Dokumentation
- **[`docs/adr/0005-dex-route-synthesis.md`](file:///f:/GateKeeper/docs/adr/0005-dex-route-synthesis.md)**: Vollständige Dokumentation der Aggregator-Integration, Parallelisierung und Ausfallsicherheit.

---

## Verifikationsbericht (Pytest: 38 von 38 Tests erfolgreich in 2.60s)

```bash
pytest -v
============================= test session starts =============================
platform win32 -- Python 3.12.7, pytest-9.1.1, pluggy-1.6.0
rootdir: F:\GateKeeper
configfile: pyproject.toml
testpaths: tests
plugins: anyio-4.13.0, asyncio-1.4.0
asyncio: mode=Mode.AUTO, debug=False
collected 38 items

tests/integration/test_api_endpoints.py (7 tests) .................... PASSED
tests/integration/test_simulation_engine.py (4 tests) ................ PASSED
tests/integration/test_sqlite_ledger.py (2 tests) .................... PASSED
tests/unit/test_abort_matrix.py (10 tests) ........................... PASSED
tests/unit/test_candidate_generator.py (5 tests) ..................... PASSED
tests/unit/test_intent_models.py (10 tests) .......................... PASSED
============================= 38 passed in 2.60s ==============================
```
