#!/usr/bin/env python3
"""
Sphene Empirical Benchmark: Suite 3 - Retrieval Latency & Concurrency Stress Test
---------------------------------------------------------------------------------
Measures:
  1. Single-thread latency distribution over 1,000 iterations:
     - Exact Entity: "Distributed Consensus Architecture"
     - Trigram / Substring: "quorum val"
     - Tag filter: "architecture"
     - Backlink resolution: "Consensus"
     Calculates: Min, Mean, Median (p50), p90, p95, p99, Max, StdDev.
  2. Concurrency stress tests:
     - 10 concurrent workers (100 requests each = 1,000 requests)
     - 50 concurrent workers (20 requests each = 1,000 requests)
     Measures: Throughput (QPS), p50/p95/p99 latency under contention,
               and SQLite WAL lock collision / error rate.
"""

import os
import sys
import time
import json
import math
import requests
import shutil
import statistics
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, "../.."))
TESTBED_DIR = os.path.join(PROJECT_ROOT, "benchmark_testbed")
VAULT_1K_DIR = os.path.join(TESTBED_DIR, "vault_1k")

# Resolve Sphene binary from PATH, standard release location, or local dev tree
SPHENE_BIN = shutil.which("sphene") or "/usr/local/bin/sphene"
if not os.path.exists(SPHENE_BIN):
    alt_bin = os.path.join(PROJECT_ROOT, "sphene_app/bin/sphene")
    if os.path.exists(alt_bin):
        SPHENE_BIN = alt_bin

BENCH_PORT = "8749"
BASE_URL = f"http://127.0.0.1:{BENCH_PORT}"
SEARCH_URL = f"{BASE_URL}/api/v1/search"

def get_api_key():
    key_file = os.path.join(VAULT_1K_DIR, ".sphene", "api.key")
    if os.path.exists(key_file):
        with open(key_file, "r") as f:
            return f.read().strip()
    return ""

def calculate_percentiles(latencies_ms):
    """Calculates min, mean, p50, p90, p95, p99, max, stddev for a list of latencies in ms."""
    s = sorted(latencies_ms)
    n = len(s)
    if n == 0:
        return {
            "count": 0, "min_ms": 0.0, "mean_ms": 0.0, "median_p50_ms": 0.0,
            "p90_ms": 0.0, "p95_ms": 0.0, "p99_ms": 0.0, "max_ms": 0.0, "stddev_ms": 0.0
        }
    
    def p(pct):
        idx = int(math.ceil((pct / 100.0) * n)) - 1
        return s[max(0, min(n - 1, idx))]

    return {
        "count": n,
        "min_ms": round(s[0], 3),
        "mean_ms": round(statistics.mean(s), 3),
        "median_p50_ms": round(statistics.median(s), 3),
        "p90_ms": round(p(90), 3),
        "p95_ms": round(p(95), 3),
        "p99_ms": round(p(99), 3),
        "max_ms": round(s[-1], 3),
        "stddev_ms": round(statistics.stdev(s) if n > 1 else 0.0, 3)
    }

def single_query_bench(session, query, iterations=1000):
    print(f"  Benchmarking single-thread latency: '{query}' ({iterations} iterations)...")
    latencies = []
    errors = 0

    # Warmup 25 queries
    for _ in range(25):
        try: session.get(SEARCH_URL, params={"q": query, "limit": 20}, timeout=1.0)
        except: pass

    t_start = time.time()
    for _ in range(iterations):
        t0 = time.perf_counter()
        try:
            r = session.get(SEARCH_URL, params={"q": query, "limit": 20}, timeout=2.0)
            t1 = time.perf_counter()
            if r.status_code == 200:
                latencies.append((t1 - t0) * 1000.0)
            else:
                errors += 1
        except Exception:
            errors += 1

    total_time = time.time() - t_start
    qps = len(latencies) / total_time if total_time > 0 else 0
    stats = calculate_percentiles(latencies)
    stats["qps"] = round(qps, 1)
    stats["errors"] = errors
    stats["error_rate_pct"] = round((errors / iterations) * 100.0, 2)
    return stats

def concurrent_bench(workers, queries_per_worker, query_list, headers=None):
    total_requests = workers * queries_per_worker
    print(f"  Benchmarking concurrency: {workers} workers x {queries_per_worker} reqs = {total_requests} total requests...")
    
    latencies = []
    errors = 0
    
    def worker_job(worker_id):
        s = requests.Session()
        if headers:
            s.headers.update(headers)
        worker_latencies = []
        worker_errors = 0
        for i in range(queries_per_worker):
            q = query_list[(worker_id + i) % len(query_list)]
            t0 = time.perf_counter()
            try:
                r = s.get(SEARCH_URL, params={"q": q, "limit": 20}, timeout=5.0)
                t1 = time.perf_counter()
                if r.status_code == 200:
                    worker_latencies.append((t1 - t0) * 1000.0)
                else:
                    worker_errors += 1
            except Exception:
                worker_errors += 1
        return worker_latencies, worker_errors

    t_start = time.time()
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = [executor.submit(worker_job, wid) for wid in range(workers)]
        for f in as_completed(futures):
            w_lats, w_errs = f.result()
            latencies.extend(w_lats)
            errors += w_errs
            
    wall_time = time.time() - t_start
    qps = len(latencies) / wall_time if wall_time > 0 else 0
    
    stats = calculate_percentiles(latencies)
    stats["workers"] = workers
    stats["wall_time_sec"] = round(wall_time, 2)
    stats["throughput_qps"] = round(qps, 1)
    stats["errors"] = errors
    stats["error_rate_pct"] = round((errors / total_requests) * 100.0, 2)
    return stats


def main():
    print("================================================================================")
    print("  Sphene Empirical Benchmark: Suite 3 (Retrieval Latency & Concurrency)         ")
    print("================================================================================")

    env = os.environ.copy()
    env["SPHENE_PORT"] = BENCH_PORT
    env["SPHENE_VAULT_DIR"] = VAULT_1K_DIR
    env["SPHENE_DB_PATH"] = os.path.join(VAULT_1K_DIR, ".sphene", "index.db")

    print("Launching Sphene daemon for retrieval benchmarks...")
    proc = subprocess.Popen([SPHENE_BIN, "daemon"], env=env,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    # Wait for daemon
    for _ in range(50):
        try:
            if requests.get(f"{BASE_URL}/api/v1/health", timeout=0.2).status_code == 200:
                break
        except:
            pass
        time.sleep(0.1)

    api_key = get_api_key()
    headers = {"Authorization": f"Bearer {api_key}", "X-Sphene-API-Key": api_key}
    session = requests.Session()
    session.headers.update(headers)
    results = {}

    try:
        print("\n--- Phase 1: Single-Thread Latency Distributions (1,000 iterations each) ---")
        queries = [
            ("Exact Entity", "Distributed Consensus Architecture"),
            ("Trigram Substring", "quorum val"),
            ("Tag Filter", "architecture"),
            ("Graph Backlinks", "Consensus")
        ]
        
        results["single_thread"] = {}
        for label, q in queries:
            res = single_query_bench(session, q, iterations=1000)
            results["single_thread"][label] = res
            print(f"    p50: {res['median_p50_ms']} ms | p95: {res['p95_ms']} ms | p99: {res['p99_ms']} ms | QPS: {res['qps']} | errors: {res['errors']}")

        print("\n--- Phase 2: Multi-Worker Concurrency Stress Tests ---")
        mixed_queries = [q for _, q in queries]
        
        # 10 workers x 100 queries = 1000 queries
        c10 = concurrent_bench(workers=10, queries_per_worker=100, query_list=mixed_queries, headers=headers)
        results["concurrency_10_workers"] = c10
        print(f"  10 Workers: Throughput {c10['throughput_qps']} QPS | p50: {c10['median_p50_ms']} ms | p95: {c10['p95_ms']} ms | Lock Contention: {c10['error_rate_pct']}%")

        # 50 workers x 20 queries = 1000 queries
        c50 = concurrent_bench(workers=50, queries_per_worker=20, query_list=mixed_queries, headers=headers)
        results["concurrency_50_workers"] = c50
        print(f"  50 Workers: Throughput {c50['throughput_qps']} QPS | p50: {c50['median_p50_ms']} ms | p95: {c50['p95_ms']} ms | Lock Contention: {c50['error_rate_pct']}%")

    finally:
        proc.terminate()
        try: proc.wait(timeout=3)
        except: proc.kill()
        print("\nSphene daemon terminated.")

    out_file = os.path.join(TESTBED_DIR, "suite3_retrieval_concurrency.json")
    with open(out_file, "w") as f:
        json.dump(results, f, indent=2)

    print("\n================================================================================")
    print("  SUITE 3 RESULTS SUMMARY TABLE                                                 ")
    print("================================================================================")
    print(f"{'Query / Workload':<32} | {'Min (ms)':<9} | {'p50 (ms)':<9} | {'p95 (ms)':<9} | {'p99 (ms)':<9} | {'QPS':<8} | {'Errors'}")
    print("-" * 92)
    for label, s in results["single_thread"].items():
        print(f"{label:<32} | {s['min_ms']:<9.2f} | {s['median_p50_ms']:<9.2f} | {s['p95_ms']:<9.2f} | {s['p99_ms']:<9.2f} | {s['qps']:<8.0f} | {s['errors']}")
    print("-" * 92)
    c10 = results["concurrency_10_workers"]
    print(f"{'10 Concurrent Workers':<32} | {c10['min_ms']:<9.2f} | {c10['median_p50_ms']:<9.2f} | {c10['p95_ms']:<9.2f} | {c10['p99_ms']:<9.2f} | {c10['throughput_qps']:<8.0f} | {c10['errors']} ({c10['error_rate_pct']}%)")
    c50 = results["concurrency_50_workers"]
    print(f"{'50 Concurrent Workers':<32} | {c50['min_ms']:<9.2f} | {c50['median_p50_ms']:<9.2f} | {c50['p95_ms']:<9.2f} | {c50['p99_ms']:<9.2f} | {c50['throughput_qps']:<8.0f} | {c50['errors']} ({c50['error_rate_pct']}%)")
    print("=" * 92)
    print(f"Raw results exported to: {out_file}")

if __name__ == "__main__":
    main()
