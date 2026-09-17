# Project Gatekeeper – Technische Architektur-Spezifikation & Implementierungsplan

## Status: Schritt 1 – Pflichtenheft & Architektur-Audit

Gatekeeper ist eine deterministische Pre-Flight-Execution-Layer und Middleware für Solana. Sie fängt Transaktions-Intents autonomer Trading- und KI-Agenten ab, generiert parallele Routenkandidaten, simuliert diese gegen den Live-State des Solana-Clusters und entscheidet deterministisch über Dispatch, Optimierung oder Hard-Abort.

---

## 1. Komponenten-Architektur (Pipeline-Design)

```
[ KI-Agent / Trader Client ]
            │  (REST / WebSocket IntentRequest)
            ▼
┌─────────────────────────────────────────────────────────────┐
│ 1. INGESTION & INTENT NORMALIZER (FastAPI / Pydantic v2)    │
│  - Validierung des Intents (Signatur, Format, Bounds)       │
│  - Slot-Synchronisation & Blockhash-Cache                   │
└──────────────────────────┬──────────────────────────────────┘
                           │
            ┌──────────────┴──────────────┐
            ▼                             ▼
┌──────────────────────────┐  ┌───────────────────────────────┐
│ 2. ROUTE CANDIDATE       │  │ 3. SOLANA CLUSTER MONITOR     │
│    GENERATOR             │  │  - WSS Slot/Blockhash Stream  │
│  - Candidate A: Direct   │  │  - Dynamic Priority Fee Estim.│
│  - Candidate B: Split    │  │  - Contended Accounts Cache   │
│  - Candidate C: Multi-Hop│  └───────────────┬───────────────┘
└───────────┬──────────────┘                  │
            │ (2-3 Unsigned/Partially Signed) │
            ▼                                 │
┌─────────────────────────────────────────────┴───────────────┐
│ 4. PRE-FLIGHT SIMULATION ENGINE (asyncio.gather)            │
│  - Parallele Ausführung via simulateTransaction (RPC/WSS)   │
│  - sigVerify: false, accountsBase64, replaceBlockhash: false│
│  - Parsing von Execution Logs & Token Balance Changes       │
└──────────────────────────┬──────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│ 5. DETERMINISTIC ARBITRATION & CLAMPING MATRIX              │
│  - Evaluation der Abbruchkriterien (Slippage, Contention)   │
│  - Dynamic Compute-Budget Clamping (CU Limit = Logs + 12%)  │
│  - Priority Fee Tuning (Micro-Lamports per CU)              │
└──────────────┬───────────────────────────────┬──────────────┘
               │ (Best Route Valid)            │ (All Routes Invalid / Abort)
               ▼                               ▼
┌──────────────────────────────┐ ┌─────────────────────────────┐
│ 6. DISPATCH LAYER            │ │ 7. HARD-DROP & SAVINGS RECORDER
│  - Jito Bundle Direct / TPU  │ │  - Sofortiger Abbruch (0 Gas)
│  - Leader Schedule Aware     │ │  - Audit-Log: Gerettete Fee │
└──────────────┬───────────────┘ └─────────────┬───────────────┘
               │                               │
               └───────────────┬───────────────┘
                               ▼
┌─────────────────────────────────────────────────────────────┐
│ 8. VPS AUDIT- & METRICS-LEDGER (SQLite / WAL Mode)          │
│  - Intent-, Simulations- & Einsparungs-Protokoll            │
│  - Prom-Metrics / Dashboard-Schnittstelle                   │
└─────────────────────────────────────────────────────────────┘
```

### Pipeline-Laufzeitphasen
1. **Ingestion & Normalisierung**:
   - Empfang von `IntentRequest` (In-Token, Out-Token, Amount, Max-Slippage, Max-Fee, TTL in Slots).
   - Validierung der Intent-Grenzen, Account-Signaturen und Whitelists.
2. **Kandidaten-Synthese**:
   - Asynchrone Erstellung von bis zu 3 Routenkandidaten (z. B. Direct-Pool Raydium, Multi-Hop Orca Whirlpool, Aggregated Route).
3. **Parallele Pre-Flight Simulation**:
   - `asyncio.gather` führt `simulateTransaction` parallel gegen High-Performance RPC-Knoten aus.
   - Extraktion von:
     - Execution Units (`consumedUnits`)
     - Log Messages (`Program log: ...`)
     - Pre- und Post-Token-Balances
     - Return Data & Inner Instructions
4. **Deterministische Schiedsgericht-Logik (Arbitration)**:
   - Filterung gescheiterter Pfade.
   - Rank-Metrik: Höchster Netto-Ertrag abzüglich minimaler berechneter Transaktions- und Priority-Kosten.
   - Dynamisches Injezieren der `ComputeBudgetProgram`-Instructions:
     - `SetComputeUnitLimit(consumed_cu * 1.12)`
     - `SetComputeUnitPrice(dynamic_micro_lamports)`
5. **Dispatch oder Drop**:
   - Wenn ein valider Pfad existiert: Signierung/Finalisierung und Übermittlung (z. B. via Jito Block-Engine oder direktes Quic/TPU).
   - Wenn alle Pfade scheitern: **Hard-Drop**. Keine On-Chain-Transaktion wird gesendet.

---

## 2. Deterministische Abbruchmatrix (Hard-Drop Criteria)

Transaktionen werden ohne Ausnahme auf der Middleware abgebrochen (`ABORT`), wenn eines der folgenden Kriterien anschlägt:

| Fehler-Code | Kriterium | Erkennungsmethode | Schwellenwert / Regel |
|---|---|---|---|
| `ERR_BLOCKHASH_EXPIRED` | Blockhash TTL Überschreitung | Cache der letzten 150 Slots via WSS `slotSubscribe`. Differenz zwischen `intent.valid_until_slot` bzw. `blockhash_slot` und aktuellem Cluster-Slot. | `current_slot - blockhash_slot >= 120` oder `current_slot > intent.valid_until_slot` |
| `ERR_SLIPPAGE_EXCEEDED` | Min-Output Unterdeckung | Differenz aus `postTokenBalances` minus `preTokenBalances` für die Destination-Wallet aus der Simulation. | `actual_delta_out < expected_min_out` |
| `ERR_ACCOUNT_CONTENTION` | Account-Locking & Hotspot | Simulation wirft `AccountInUse` ODER Writable Accounts gehören zu bekannten Congested Pools mit Write-Lock-Wait > Grenzwert. | RPC-Error `AccountInUse` oder Write-Lock-Contention im Mempool-Tracker |
| `ERR_CU_EXHAUSTION` | Compute-Budget Überlauf | Simulations-Log enthält `Program failed to complete: consumed X of Y compute units` oder `consumedUnits > intent.max_compute_units`. | `consumed_cu > intent.max_compute_units` |
| `ERR_RENT_NON_EXEMPT` | Rent-Unterdeckung / Balance | Verbleibende native SOL-Balance der Fee-Payer-Wallet nach Abzug von Base-Fee, Priority-Fee und Rent-Exempt-Minimum. | `post_sol_balance < rent_exempt_minimum` |
| `ERR_INSUFFICIENT_FUNDS` | Mangelnde Quellmittel | Pre-Simulation Balance-Check der Source-Token. | `source_balance < required_amount_in` |
| `ERR_CUSTOM_PROGRAM_FAIL` | Anchor/AMM Fehlercode | Parsing der Program-Logs nach Fehlermustern (z. B. Raydium `0x1771` Slippage, Whirlpool `0x1770`). | Regex-Treffer auf `InstructionError` / Custom Error Hex |

---

## 3. Datenbankschema für VPS Audit-Logging & Einsparungs-Metriken

Eingesetzter Stack: **SQLite im WAL-Modus (Write-Ahead Logging)** mit Memory-Mapped I/O für Sub-Millisekunden-Schreibvorgänge.

### Tabellen-Spezifikation (DDL)

```sql
-- 1. Intent Requests (Eingehende Handelsabsichten)
CREATE TABLE IF NOT EXISTS intents (
    intent_id TEXT PRIMARY KEY,
    agent_id TEXT NOT NULL,
    input_mint TEXT NOT NULL,
    output_mint TEXT NOT NULL,
    amount_in INTEGER NOT NULL,
    min_amount_out INTEGER NOT NULL,
    max_slippage_bps INTEGER NOT NULL,
    max_priority_fee_lamports INTEGER NOT NULL,
    created_at_slot INTEGER NOT NULL,
    valid_until_slot INTEGER NOT NULL,
    received_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    status TEXT NOT NULL -- 'DISPATCHED', 'DROPPED', 'EXPIRED'
);

-- 2. Route Candidates (Generierte Pfade je Intent)
CREATE TABLE IF NOT EXISTS route_candidates (
    candidate_id TEXT PRIMARY KEY,
    intent_id TEXT NOT NULL,
    dex_type TEXT NOT NULL, -- 'RAYDIUM', 'ORCA', 'METEORA', 'SPLIT'
    route_plan_json TEXT NOT NULL,
    is_split BOOLEAN DEFAULT FALSE,
    FOREIGN KEY(intent_id) REFERENCES intents(intent_id) ON DELETE CASCADE
);

-- 3. Simulation Results (Simulations-Rohdaten)
CREATE TABLE IF NOT EXISTS simulations (
    simulation_id TEXT PRIMARY KEY,
    candidate_id TEXT NOT NULL,
    success BOOLEAN NOT NULL,
    consumed_units INTEGER,
    simulated_delta_out INTEGER,
    error_code TEXT,
    error_log TEXT,
    simulation_duration_ms REAL NOT NULL,
    simulated_at_slot INTEGER NOT NULL,
    simulated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(candidate_id) REFERENCES route_candidates(candidate_id) ON DELETE CASCADE
);

-- 4. Audit & Fee Savings Ledger (Nachweisbare Metriken)
CREATE TABLE IF NOT EXISTS fee_savings_ledger (
    ledger_id INTEGER PRIMARY KEY AUTOINCREMENT,
    intent_id TEXT NOT NULL,
    action_taken TEXT NOT NULL, -- 'DISPATCHED', 'HARD_ABORT'
    selected_candidate_id TEXT,
    aborted_candidates_count INTEGER NOT NULL,
    base_fee_saved_lamports INTEGER DEFAULT 0,
    priority_fee_saved_lamports INTEGER DEFAULT 0,
    capital_saved_lamports INTEGER DEFAULT 0,
    clamped_cu_saved_units INTEGER DEFAULT 0,
    decision_latency_ms REAL NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(intent_id) REFERENCES intents(intent_id)
);

CREATE INDEX IF NOT EXISTS idx_intents_agent ON intents(agent_id);
CREATE INDEX IF NOT EXISTS idx_simulations_candidate ON simulations(candidate_id);
CREATE INDEX IF NOT EXISTS idx_savings_action ON fee_savings_ledger(action_taken);
```

### Berechnung der Einsparungs-Metrik
- **Priority Fee gerettet**:
  $$\text{Saved Priority Fee} = \sum_{\text{aborted}} \left(\frac{\text{Clamped CU Limit} \times \text{Priority Fee Rate}}{10^6}\right) + \text{Base Fee (5.000 Lamports)}$$
- **Verbranntes Kapital verhindert**:
  Wenn Slippage-Fail auf On-Chain-Ebene zu schlechterem Fill geführt hätte bzw. Revert-Strafen vermieden wurden.
- **Compute Unit Clamping Optimierung**:
  Differenz zwischen Default-Limit (z. B. 200.000 CU) und geklemmtem Limit ($\text{Consumed CU} \times 1.12$).

---

## 4. Struktur des Projekt-Repositories inklusive Test-Harness

```
GateKeeper/
├── .github/
│   └── workflows/
│       └── ci.yml                     # Test suite, linting, type checks
├── docs/
│   ├── adr/                           # Architecture Decision Records
│   │   ├── 0001-record-architecture-decisions.md
│   │   ├── 0002-async-rpc-simulation-gather.md
│   │   ├── 0003-deterministic-abort-matrix.md
│   │   └── 0004-sqlite-wal-audit-ledger.md
│   ├── spec/
│   │   ├── openapi_gatekeeper.yaml    # REST & WebSocket API-Spezifikation
│   │   └── abort_matrix_reference.md  # Deterministische Fehlercodes
│   └── benchmarks/
│       └── latency_baseline.md
├── src/
│   └── gatekeeper/
│       ├── __init__.py
│       ├── config.py                  # Pydantic Settings (RPC, Keys, Limits)
│       ├── main.py                    # FastAPI Service Entrypoint
│       ├── api/                       # Router für REST & WS
│       │   ├── __init__.py
│       │   ├── v1/
│       │   │   ├── intents.py         # POST /api/v1/intent, GET /api/v1/intent/{id}
│       │   │   └── metrics.py         # GET /api/v1/metrics/savings
│       │   └── websockets.py          # Realtime Intent Stream & Feedback
│       ├── core/                      # Kern-Modelle & Interfaces
│       │   ├── __init__.py
│       │   ├── models.py              # IntentRequest, RouteCandidate, ValidationResult
│       │   └── exceptions.py          # GatekeeperAbortException, etc.
│       ├── engine/                    # Pre-Flight Simulations-Engine
│       │   ├── __init__.py
│       │   ├── candidate_generator.py # Route-Synthese (Direct / Split / Multi-Hop)
│       │   ├── simulator.py           # Parallel simulateTransaction Worker
│       │   ├── buffer_clamping.py     # Dynamischer CU-Clamping-Algorithmus
│       │   └── arbitrator.py          # Schiedsrichter & Matrix-Evaluierung
│       ├── matrix/                    # Deterministische Validatoren
│       │   ├── __init__.py
│       │   ├── ttl_validator.py       # Slot & Blockhash Gültigkeit
│       │   ├── slippage_validator.py  # Balance Delta Checker
│       │   ├── contention_checker.py  # Writable Account Lock Analyzer
│       │   └── rent_validator.py      # Sol Balance & Rent Exemption
│       ├── storage/                   # VPS Persistenz
│       │   ├── __init__.py
│       │   ├── database.py            # SQLite async (aiosqlite) Connection Pool
│       │   ├── models.py              # ORM / Table Mapping
│       │   └── repository.py          # Ledger Schreib- & Leseoperationen
│       └── cluster/                   # Solana Node & Network Adapter
│           ├── __init__.py
│           ├── rpc_client.py          # Resilient RPC Client mit Failover
│           └── slot_subscriber.py     # WSS Slot & Blockhash Live-Sync
├── tests/
│   ├── __init__.py
│   ├── conftest.py                    # Pytest Fixtures & RPC Mocking Harness
│   ├── unit/
│   │   ├── test_clamping.py           # CU Clamping Berechnungen
│   │   ├── test_abort_matrix.py       # Validatoren (TTL, Slippage, Contention)
│   │   └── test_intent_models.py      # Pydantic Schema-Validierung
│   ├── integration/
│   │   ├── test_simulation_engine.py  # Asynchrones asyncio.gather Mocking
│   │   ├── test_sqlite_ledger.py      # Datenbank-Transaktionen & Einsparungsrechnung
│   │   └── test_api_endpoints.py      # FastAPI TestClient Intent-Flows
│   └── fixtures/
│       ├── simulation_responses/      # Echte Solana RPC Simulation JSON-Dumps
│       │   ├── raydium_success.json
│       │   ├── slippage_failure.json
│       │   ├── cu_exceeded.json
│       │   └── account_locked.json
│       └── blockhashes.json
├── pyproject.toml                     # Poetry / uv Projektdefinition
├── README.md
└── ruff.toml                          # Linting & Formatting Regeln
```

---

## 5. Test-Harness & Verifikations-Strategie (TDD)

1. **RPC-Simulation-Mocking (Zero-Cost Testing)**:
   - Einbindung von echten Solana-Simulation-JSON-Payloads als Fixtures.
   - Mocking extremer Netzwerkkonflikte:
     - Simulation von Netzwerk-Jitter (50ms bis 500ms).
     - Parallele Simulationen, bei denen Route 1 fehlschlägt (`0x1771`), Route 2 an CU-Limit scheitert, und Route 3 optimal durchgeht.
2. **Invarianz-Prüfungen**:
   - **Garantie**: Keine Transaktion mit berechnetem negativen Ertrag oder Slippage-Verletzung darf jemals `DISPATCHED` als Status erhalten.
   - **Garantie**: Das CU-Limit ist immer strikt geclamped ($\text{Consumed} \times 1.10 \le \text{Clamped} \le \text{Consumed} \times 1.25$).
3. **VPS-Ressourcen-Effizienz**:
   - SQLite WAL-Benchmark: Bis zu 10.000 Inserts/Sekunde ohne Blockieren der Simulations-Event-Loop.

---

## Nächste Schritte (Nach Bestätigung von Schritt 1)
- Initialisierung des Repositories mit `pyproject.toml`, Ordnerstruktur und Basiskonfiguration.
- Hinterlegung des ersten Satzes von Architecture Decision Records (ADRs).
- Erstellung der Core-Datenstrukturen (`IntentRequest`, `RouteCandidate`, `ValidationResult`) mit begleitenden Pydantic-Tests.
