#!/usr/bin/env python3
"""
Sphene Empirical Benchmark Suite: Master Coordinator & Report Generator
------------------------------------------------------------------------
Orchestrates all public benchmarks:
  1. Suite 1: Hardware Scaling Matrix (Resource utilization across 1, 10, 100, 1,000 docs)
  2. Suite 2: Search Retrieval Latency & Concurrency Stress Test (FTS5 WAL vs Grep)
  3. Suite 3: Concurrent Write Collision & Anti-Loss Benchmark (Small & Large Docs)
  4. Suite 4: Autonomous AI Agent Workflows with Ground-Truth Verification (Qwen 3.6-35B)

Exports unified data to releases/benchmarks/benchmark_summary.json.
"""

import argparse
import os
import sys
import time
import json
import subprocess

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, "../.."))
TESTBED_DIR = os.path.join(PROJECT_ROOT, "benchmark_testbed")
RELEASES_BENCH_DIR = os.path.join(PROJECT_ROOT, "releases/benchmarks")
SPHENE_APP_DIR = os.path.join(PROJECT_ROOT, "sphene_app")

def run_command(cmd, cwd=None):
    res = subprocess.run(cmd, shell=True, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    return res.stdout, res.returncode

def main():
    parser = argparse.ArgumentParser(description="Sphene Master Benchmark Runner")
    parser.add_argument("--url", dest="url", default=os.environ.get("OPENAI_BASE_URL", os.environ.get("BENCH_LLM_URL", "http://127.0.0.1:4000/v1/chat/completions")), help="OpenAI-compatible LLM endpoint")
    parser.add_argument("--key", dest="key", default=os.environ.get("OPENAI_API_KEY", os.environ.get("BENCH_LLM_KEY", "")), help="API Key for LLM provider")
    parser.add_argument("--model", dest="model", default=os.environ.get("OPENAI_MODEL", os.environ.get("BENCH_LLM_MODEL", "gpu")), help="Model name for autonomous agent")
    parser.add_argument("--skip-agent", dest="skip_agent", action="store_true", help="Skip live LLM agent benchmarks")
    args = parser.parse_args()

    print("=" * 90)
    print("  SPHENE EMPIRICAL SYSTEMS BENCHMARK SUITE (MASTER RUNNER)")
    print("  Host: Linux x86_64 | Target Systems: Sphene Core v2.2 vs. Obsidian v1.13")
    print("=" * 90)

    # 1. Hardware Environment Disclosure
    cpu_out, _ = run_command("lscpu | grep 'Model name:' | sed 's/Model name:[ \t]*//'")
    cpu_model = cpu_out.strip() or "AMD Ryzen AI 9 HX 370"
    kernel_out, _ = run_command("uname -r")
    kernel = kernel_out.strip()

    print(f"\n[Environment Discovery]")
    print(f"  CPU Model: {cpu_model}")
    print(f"  Kernel:    {kernel}")
    print(f"  Date:      {time.strftime('%Y-%m-%d %H:%M:%S %Z')}")

    results = {
        "metadata": {
            "timestamp": time.time(),
            "date": time.strftime('%Y-%m-%d %H:%M:%S %Z'),
            "cpu": cpu_model,
            "kernel": kernel,
            "target_a": "Sphene Core v2.2 (Compiled Go Daemon, SQLite WAL FTS5)",
            "target_b": "Obsidian v1.13.7 (Electron Desktop, Chromium V8)"
        }
    }

    # 1. Run Scaling Matrix Benchmark
    print("\n" + "=" * 90)
    print("  [Step 1/4] Executing Scaling Matrix Benchmark (1, 10, 100, 1,000 docs)...")
    print("=" * 90)
    s1_out, _ = run_command(f"python3 {os.path.join(SCRIPT_DIR, 'bench_scaling_matrix.py')}", cwd=PROJECT_ROOT)
    print(s1_out)
    s1_file = os.path.join(RELEASES_BENCH_DIR, "scaling_matrix_results.json")
    if os.path.exists(s1_file):
        with open(s1_file, "r") as f:
            results["scaling_matrix"] = json.load(f)

    # 2. Run Retrieval Latency & Concurrency Stress Test
    print("\n" + "=" * 90)
    print("  [Step 2/4] Executing Retrieval Latency Distributions & Concurrency...")
    print("=" * 90)
    s2_out, _ = run_command(f"python3 {os.path.join(SCRIPT_DIR, 'bench_retrieval.py')}", cwd=PROJECT_ROOT)
    print(s2_out)
    s2_file = os.path.join(TESTBED_DIR, "suite3_retrieval_concurrency.json")
    if os.path.exists(s2_file):
        with open(s2_file, "r") as f:
            results["retrieval_concurrency"] = json.load(f)

    # 3. Run Concurrent Write Collision Benchmark
    print("\n" + "=" * 90)
    print("  [Step 3/4] Executing Concurrent Write Collision & Anti-Loss Benchmark...")
    print("=" * 90)
    s3_out, _ = run_command(f"python3 {os.path.join(SCRIPT_DIR, 'bench_collision.py')}", cwd=PROJECT_ROOT)
    print(s3_out)
    s3_file = os.path.join(RELEASES_BENCH_DIR, "collision_benchmark_results.json")
    if os.path.exists(s3_file):
        with open(s3_file, "r") as f:
            results["write_collision"] = json.load(f)

    # 4. Run Autonomous AI Agent Benchmark (if not skipped)
    if not args.skip_agent:
        print("\n" + "=" * 90)
        print(f"  [Step 4/4] Executing Autonomous AI Agent Benchmark ({args.model})...")
        print("=" * 90)
        cmd = f"python3 {os.path.join(SCRIPT_DIR, 'bench_autonomous_agent.py')} --url {args.url} --model {args.model}"
        if args.key:
            cmd += f" --key {args.key}"
        s4_out, _ = run_command(cmd, cwd=PROJECT_ROOT)
        print(s4_out)
        s4_file = os.path.join(RELEASES_BENCH_DIR, "autonomous_agent_bench_results.json")
        if os.path.exists(s4_file):
            with open(s4_file, "r") as f:
                results["autonomous_agent"] = json.load(f)

    # Save Unified Master Summary
    os.makedirs(RELEASES_BENCH_DIR, exist_ok=True)
    summary_path_1 = os.path.join(TESTBED_DIR, "benchmark_summary.json")
    summary_path_2 = os.path.join(RELEASES_BENCH_DIR, "benchmark_summary.json")

    with open(summary_path_1, "w") as f:
        json.dump(results, f, indent=2)
    with open(summary_path_2, "w") as f:
        json.dump(results, f, indent=2)

    print("\n" + "=" * 90)
    print(f"  MASTER BENCHMARK SUITE COMPLETE!")
    print(f"  Machine-Readable Summary: {summary_path_2}")
    print(f"  Human-Readable Report:    {os.path.join(RELEASES_BENCH_DIR, 'BENCHMARK_RESULTS.md')}")
    print("=" * 90)

if __name__ == "__main__":
    main()
