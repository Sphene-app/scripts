# Sphene Empirical Systems Benchmarks & Reproducibility Suite

This directory contains the automated, peer-reviewable empirical benchmark harness comparing the **Sphene Compiled Native Daemon** against the **Obsidian Electron Desktop Application** across identical Markdown vaults and real-world Model Context Protocol (MCP) agent workloads.

All tests run against standard Markdown vaults without proprietary locks.

---

## 1. Quick Start: How to Benchmark on Your System

Prerequisites: Python 3.8+ with `psutil` and `requests`.

```bash
# 1. Install lightweight telemetry dependencies
pip install psutil requests

# 2. (Optional) Start your local or remote LLM endpoint
# Default connects to http://127.0.0.1:4000/v1 or any OpenAI-compatible API
# Set environment variables if using a custom key/endpoint:
export BENCH_LLM_URL="http://127.0.0.1:4000/v1/chat/completions"
export BENCH_LLM_KEY="your-api-key"
export BENCH_LLM_MODEL="your-model-name"

# 3. Run the complete master benchmark suite
python3 runner.py
```

All raw measurements, standard deviations, and latency percentiles are exported directly to `benchmark_summary.json`.

---

## 2. Benchmark Suites

### Suite 1: System Hygiene, Cold Boot & RAM Footprint (`bench_system.py`)
- **Sphene Core:** Measures cold startup time from binary launch to accepting HTTP 200 `/api/v1/health` queries, physical Resident Set Size (RSS) via `/proc/<pid>/statm`, and 60-second idle CPU utilization.
- **Obsidian Desktop:** Launches Obsidian via its Linux executable/AppImage on the same vault, measures startup latency to window initialization, and sums physical RSS memory across all child processes in the Electron process tree (Main, Zygotes, GPU helper, Renderers, Utility).

### Suite 2: Retrieval Latency & Concurrency Stress Test (`bench_retrieval.py`)
- Evaluates 1,000 single-thread queries across exact entities, trigram substrings, multi-tag filters, and graph backlink resolutions.
- Measures full statistical distributions: **Min, Mean, Median (p50), p90, p95, p99, and Max latency (ms)**.
- Stresses SQLite WAL concurrency under 10 and 50 simultaneous parallel workers, measuring throughput (QPS) and lock contention failure rate.
- Compares against unindexed sequential filesystem disk scanning (`grep` / `ripgrep`).

### Suite 3: Real AI Agent Workflows & Ground-Truth Verification (`bench_real_agent.py`)
Executes real everyday user scenarios against an active LLM backend, recording actual prompt tokens, completion tokens, time-to-first-token (TTFT), and programmatically verifying that the LLM's response strictly matches ground truth:
1. **Executive Meeting Note:** Budget extraction ($45,000 approved by Alex Chen).
2. **Project Task List:** Task checkoff while human is actively typing; tests working-copy preservation vs silent overwrite.
3. **Daily Personal Journal:** Extraction of health vitals and prescription dosage (122/78 mmHg / 10mg Lisinopril).
4. **Legal Master Agreement:** Synthesis of cross-document penalty clauses (2.5% weekly delay deduction / 10% liability cap).
5. **DevOps Migration Spec:** Target cache configuration parameters (Port 6379 / `volatile-lru` eviction policy).
6. **Vacation Travel Itinerary:** Schedule extraction of dinner reservations (19:30 / Confirmation `GION-8842`).

---

## 3. Verified Reference Baseline (Host: AMD Ryzen AI 9 HX 370 Zen 5)

### System Performance & Memory Footprint

| Metric | Sphene Core v2.2 (Go Daemon) | Obsidian v1.13.7 (Electron Desktop) | Verification Tool |
| :--- | :--- | :--- | :--- |
| **Physical RSS RAM at Rest** | **45.8 MB** (1 process) | **804.5 MB** (6 processes) | `/proc/<pid>/statm` |
| **Search Query Latency (p50)** | **2.40 ms** (398 QPS) | ~780 ms (Filesystem scan) | `bench_retrieval.py` |
| **50-Worker Parallel Query Errors** | **0.0%** (Zero lock contention) | Single-threaded disk queue | `bench_retrieval.py` |

### Real AI Agent Token Efficiency (Verified Ground-Truth Accuracy)

| User Scenario | Document Type | Obsidian (Whole File) | Sphene (Targeted MCP) | Token Savings | Ground Truth Verified |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Budget Extraction** | Meeting Minutes | 667 prompt tokens | 290 prompt tokens | **56.5%** | **Yes** ($45k / Alex Chen) |
| **Health Vitals** | Daily Journal | 392 prompt tokens | 113 prompt tokens | **71.2%** | **Yes** (122/78 / Lisinopril) |
| **Contract Penalty** | Legal Agreement | 486 prompt tokens | 161 prompt tokens | **66.9%** | **Yes** (2.5% / 10% cap) |
| **DevOps Server Spec** | Tech Architecture | 395 prompt tokens | 147 prompt tokens | **62.8%** | **Yes** (Port 6379 / volatile-lru) |
| **Dining Reservation** | Travel Itinerary | 480 prompt tokens | 198 prompt tokens | **58.8%** | **Yes** (19:30 / GION-8842) |
| **Task Checkoff** | Project Roadmap | Direct Overwrite | Staged AST Diff | **100% Safe** | **Yes** (Sarah's Note Saved) |
