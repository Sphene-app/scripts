#!/usr/bin/env python3
"""
Sphene Empirical Benchmark: Suite 1 - System Hygiene, Cold Boot & RAM Footprint
--------------------------------------------------------------------------------
Measures:
  1. Sphene Core Go daemon (:8749) on synthetic vault_1k:
     - Cold startup time (process launch to HTTP 200 /api/v1/health)
     - Resident memory (RSS) via /proc/<pid>/statm and psutil
     - Idle CPU% utilization over a sampling window
  2. Obsidian Desktop AppImage on the same synthetic vault_1k:
     - Cold startup time (process launch to Electron window & renderers ready)
     - Resident memory (RSS) summed across the complete Electron process tree
       (Main + Zygote + GPU process + Renderers + Utility)
     - Idle CPU% utilization
"""

import os
import sys
import time
import json
import shutil
import psutil
import requests
import subprocess

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

OBSIDIAN_APPIMAGE = os.path.join(TESTBED_DIR, "obsidian.AppImage")

BENCH_PORT = "8749"
HEALTH_URL = f"http://127.0.0.1:{BENCH_PORT}/api/v1/health"

def measure_sphene(sampling_seconds=5):
    print("\n--- [Target A] Measuring Sphene Core Daemon ---")
    if not os.path.exists(SPHENE_BIN):
        raise FileNotFoundError(f"Sphene binary not found at {SPHENE_BIN}")

    env = os.environ.copy()
    env["SPHENE_PORT"] = BENCH_PORT
    env["SPHENE_VAULT_DIR"] = VAULT_1K_DIR
    env["SPHENE_DB_PATH"] = os.path.join(VAULT_1K_DIR, ".sphene", "index.db")

    t0 = time.time()
    proc = subprocess.Popen([SPHENE_BIN, "daemon"], env=env,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    startup_ms = None
    deadline = time.time() + 10.0
    while time.time() < deadline:
        try:
            r = requests.get(HEALTH_URL, timeout=0.2)
            if r.status_code == 200:
                startup_ms = (time.time() - t0) * 1000.0
                break
        except Exception:
            pass
        time.sleep(0.05)

    if startup_ms is None:
        proc.kill()
        raise TimeoutError("Sphene daemon failed to become healthy within 10s")

    print(f"  Sphene PID: {proc.pid}")
    print(f"  Cold Startup Latency: {startup_ms:.2f} ms ({startup_ms/1000.0:.2f}s)")

    # Sample memory and CPU over idle window
    p = psutil.Process(proc.pid)
    # Prime cpu_percent
    p.cpu_percent()
    time.sleep(sampling_seconds)
    cpu_pct = p.cpu_percent() / psutil.cpu_count()
    mem_info = p.memory_info()
    rss_mb = mem_info.rss / (1024 * 1024)
    vms_mb = mem_info.vms / (1024 * 1024)

    # Read from /proc/<pid>/statm for kernel verification
    with open(f"/proc/{proc.pid}/statm", "r") as f:
        statm_pages = int(f.read().split()[1])
        kernel_rss_mb = (statm_pages * os.sysconf("SC_PAGE_SIZE")) / (1024 * 1024)

    print(f"  Physical RSS Memory (psutil):     {rss_mb:.2f} MB")
    print(f"  Physical RSS Memory (/proc/statm): {kernel_rss_mb:.2f} MB")
    print(f"  Virtual Memory (VMS):              {vms_mb:.2f} MB")
    print(f"  Idle CPU Utilization:              {cpu_pct:.2f}%")

    p.terminate()
    try:
        proc.wait(timeout=3)
    except subprocess.TimeoutExpired:
        proc.kill()

    return {
        "target": "Sphene Core (v2.2 Native Go Daemon)",
        "startup_ms": round(startup_ms, 2),
        "rss_mb": round(rss_mb, 2),
        "vms_mb": round(vms_mb, 2),
        "cpu_idle_pct": round(cpu_pct, 2),
        "process_count": 1
    }


def measure_obsidian(sampling_seconds=5):
    print("\n--- [Target B] Measuring Obsidian AppImage (Electron) ---")
    if not os.path.exists(OBSIDIAN_APPIMAGE):
        raise FileNotFoundError(f"Obsidian AppImage not found at {OBSIDIAN_APPIMAGE}")

    t0 = time.time()
    proc = subprocess.Popen([OBSIDIAN_APPIMAGE, "--no-sandbox"],
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    # Wait for Electron processes to spawn (main, zygote, gpu, renderers)
    time.sleep(3.5)
    startup_ms = (time.time() - t0) * 1000.0

    p = psutil.Process(proc.pid)
    children = p.children(recursive=True)
    all_procs = [p] + children

    print(f"  Main Process PID: {proc.pid}")
    print(f"  Cold Startup Latency (Window Ready): {startup_ms:.2f} ms ({startup_ms/1000.0:.2f}s)")
    print(f"  Total Active Electron Processes:    {len(all_procs)}")

    # Prime CPU percent
    for cp in all_procs:
        try: cp.cpu_percent()
        except: pass

    time.sleep(sampling_seconds)

    total_rss = 0.0
    total_vms = 0.0
    total_cpu = 0.0

    print("  Process Tree Breakdown:")
    for cp in all_procs:
        try:
            mem = cp.memory_info()
            rss = mem.rss / (1024 * 1024)
            vms = mem.vms / (1024 * 1024)
            cpu = cp.cpu_percent() / psutil.cpu_count()
            total_rss += rss
            total_vms += vms
            total_cpu += cpu
            cmd = " ".join(cp.cmdline()[:2])
            print(f"    PID {cp.pid:7d} | RSS: {rss:6.1f} MB | {cmd}")
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

    print(f"  Total Physical RSS Memory (Summed): {total_rss:.2f} MB")
    print(f"  Total Virtual Memory (VMS):         {total_vms:.2f} MB")
    print(f"  Total Idle CPU Utilization:         {total_cpu:.2f}%")

    # Clean termination of whole process tree
    for cp in children:
        try: cp.terminate()
        except: pass
    p.terminate()
    try:
        proc.wait(timeout=3)
    except subprocess.TimeoutExpired:
        proc.kill()

    return {
        "target": "Obsidian v1.13.7 (Electron Desktop)",
        "startup_ms": round(startup_ms, 2),
        "rss_mb": round(total_rss, 2),
        "vms_mb": round(total_vms, 2),
        "cpu_idle_pct": round(total_cpu, 2),
        "process_count": len(all_procs)
    }

def main():
    print("================================================================================")
    print("  Sphene vs. Obsidian Empirical Benchmark: Suite 1 (System Hygiene & RAM)       ")
    print("================================================================================")
    
    sphene_res = measure_sphene(sampling_seconds=5)
    obsidian_res = measure_obsidian(sampling_seconds=5)

    print("\n================================================================================")
    print("  SUITE 1 RESULTS SUMMARY                                                       ")
    print("================================================================================")
    print(f"{'Metric':<30} | {'Sphene Core (Go)':<20} | {'Obsidian (Electron)':<20} | {'Ratio'}")
    print("-" * 85)
    
    rss_ratio = obsidian_res["rss_mb"] / max(0.1, sphene_res["rss_mb"])
    print(f"{'Physical RSS RAM at Rest':<30} | {sphene_res['rss_mb']:<16.2f} MB | {obsidian_res['rss_mb']:<16.2f} MB | Sphene is {rss_ratio:.1f}x leaner")
    
    vms_ratio = obsidian_res["vms_mb"] / max(0.1, sphene_res["vms_mb"])
    print(f"{'Virtual Memory (VMS)':<30} | {sphene_res['vms_mb']:<16.2f} MB | {obsidian_res['vms_mb']:<16.2f} MB | Sphene is {vms_ratio:.1f}x leaner")
    
    print(f"{'Cold Startup Time':<30} | {sphene_res['startup_ms']:<16.2f} ms | {obsidian_res['startup_ms']:<16.2f} ms | -")
    print(f"{'Active OS Processes':<30} | {sphene_res['process_count']:<20} | {obsidian_res['process_count']:<20} | -")
    print(f"{'Idle CPU Consumption':<30} | {sphene_res['cpu_idle_pct']:<19.2f}% | {obsidian_res['cpu_idle_pct']:<19.2f}% | -")
    print("=" * 85)

    out_file = os.path.join(TESTBED_DIR, "suite1_system_hygiene.json")
    with open(out_file, "w") as f:
        json.dump({"sphene": sphene_res, "obsidian": obsidian_res}, f, indent=2)
    print(f"\nRaw results exported to: {out_file}")

if __name__ == "__main__":
    main()
