#!/usr/bin/env python3
"""
Sphene Empirical Scaling Matrix Benchmark
-----------------------------------------
Measures concrete, specific hardware metrics across scaling vault sizes:
  - Memory & CPU used to index 1, 10, 100, and 1,000 documents
  - Memory at rest (Resident Set Size MB) with 1, 10, 100, 1,000 documents
  - Single document Read and Write latency (ms)
  - Search latency within 100 notes vs. 1,000 notes (Sphene FTS5 vs. Grep)
"""

import os
import sys
import time
import json
import shutil
import psutil
import subprocess
import requests

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, "../.."))
TESTBED_DIR = os.path.join(PROJECT_ROOT, "benchmark_testbed")
SPHENE_BIN = shutil.which("sphene") or "/usr/local/bin/sphene"

def measure_indexing(vault_path):
    """Measures wall-clock time, peak CPU %, and peak RSS memory during vault indexing."""
    db_path = os.path.join(vault_path, ".sphene", "index.db")
    if os.path.exists(db_path):
        os.remove(db_path)

    env = os.environ.copy()
    env["SPHENE_VAULT_DIR"] = vault_path

    t0 = time.perf_counter()
    proc = subprocess.Popen([SPHENE_BIN, "index"], env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    
    p = psutil.Process(proc.pid)
    peak_rss = 0.0
    peak_cpu = 0.0

    while proc.poll() is None:
        try:
            rss = p.memory_info().rss / (1024 * 1024)
            cpu = p.cpu_percent(interval=0.01)
            if rss > peak_rss:
                peak_rss = rss
            if cpu > peak_cpu:
                peak_cpu = cpu
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            break

    proc.wait()
    wall_ms = (time.perf_counter() - t0) * 1000.0

    return {
        "index_time_ms": round(wall_ms, 2),
        "peak_rss_mb": round(peak_rss, 2),
        "peak_cpu_pct": round(peak_cpu, 1)
    }

def measure_read_write(vault_path):
    """Measures single document read time and write time."""
    test_file = os.path.join(vault_path, "Benchmark_RW_Test.md")
    content = "# Benchmark Note\n\nThis is a benchmark payload for read/write latency testing.\n" * 20
    
    # 1. Write Latency
    t0 = time.perf_counter()
    with open(test_file, "w", encoding="utf-8") as f:
        f.write(content)
        f.flush()
        os.fsync(f.fileno())
    write_ms = (time.perf_counter() - t0) * 1000.0

    # 2. Read Latency
    t0 = time.perf_counter()
    with open(test_file, "r", encoding="utf-8") as f:
        _ = f.read()
    read_ms = (time.perf_counter() - t0) * 1000.0

    # Clean up test file
    if os.path.exists(test_file):
        os.remove(test_file)

    return {
        "disk_write_ms": round(write_ms, 3),
        "disk_read_ms": round(read_ms, 3)
    }

def measure_search_speed(vault_path, query="consensus"):
    """Compares indexed SQLite FTS5 search vs. sequential filesystem grep."""
    # 1. Sequential Grep across directory
    t0 = time.perf_counter()
    grep_res = subprocess.run(["grep", "-rnI", query, vault_path], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    grep_ms = (time.perf_counter() - t0) * 1000.0

    # 2. Sphene Search via CLI
    env = os.environ.copy()
    env["SPHENE_VAULT_DIR"] = vault_path
    t0 = time.perf_counter()
    sph_res = subprocess.run([SPHENE_BIN, "search", query], env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    sph_ms = (time.perf_counter() - t0) * 1000.0

    return {
        "grep_search_ms": round(grep_ms, 2),
        "sphene_search_ms": round(sph_ms, 2)
    }

def main():
    print("=" * 85)
    print("  SPHENE EMPIRICAL SCALING MATRIX BENCHMARK")
    print("=" * 85)

    scales = [
        ("1 Document", os.path.join(TESTBED_DIR, "vault_1")),
        ("10 Documents", os.path.join(TESTBED_DIR, "vault_10")),
        ("100 Documents", os.path.join(TESTBED_DIR, "vault_100")),
        ("1,000 Documents", os.path.join(TESTBED_DIR, "vault_1k")),
    ]

    results = {}

    print(f"\n[1. Indexing & Resource Utilization Across Vault Sizes]")
    print(f"{'Vault Scale':<18} | {'Index Time (ms)':<16} | {'Peak CPU (%)':<14} | {'Peak RAM during Index'}")
    print("-" * 75)
    
    for label, vpath in scales:
        idx = measure_indexing(vpath)
        rw = measure_read_write(vpath)
        results[label] = {
            "indexing": idx,
            "read_write": rw
        }
        print(f"{label:<18} | {idx['index_time_ms']:<16} | {idx['peak_cpu_pct']:<14} | {idx['peak_rss_mb']} MB")

    print("\n[2. Search Latency Comparison: 100 Notes vs. 1,000 Notes]")
    print(f"{'Vault Scale':<18} | {'Filesystem Grep (ms)':<22} | {'Sphene Indexed Search (ms)':<28} | {'Speedup'}")
    print("-" * 85)

    for label, vpath in [("100 Documents", scales[2][1]), ("1,000 Documents", scales[3][1])]:
        s = measure_search_speed(vpath, query="consensus")
        results[label]["search"] = s
        speedup = round(s["grep_search_ms"] / max(s["sphene_search_ms"], 0.01), 1)
        print(f"{label:<18} | {s['grep_search_ms']:<22} | {s['sphene_search_ms']:<28} | {speedup}x faster")

    print("\n[3. Single Document File I/O Baseline]")
    rw_1k = results["1,000 Documents"]["read_write"]
    print(f"  • Single Note Read Latency:  {rw_1k['disk_read_ms']} ms")
    print(f"  • Single Note Write Latency: {rw_1k['disk_write_ms']} ms (with flush & fsync)")

    out_file = os.path.join(PROJECT_ROOT, "releases/benchmarks/scaling_matrix_results.json")
    with open(out_file, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nResults saved to: {out_file}")

if __name__ == "__main__":
    main()
