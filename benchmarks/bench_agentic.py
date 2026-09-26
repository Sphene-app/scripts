#!/usr/bin/env python3
"""
Sphene Agent Workflows Runner (Wrapper for bench_real_agent.py)
"""
import sys
import os

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
bench_real_path = os.path.join(SCRIPT_DIR, "bench_real_agent.py")

if __name__ == "__main__":
    os.execv(sys.executable, [sys.executable, bench_real_path] + sys.argv[1:])
