#!/usr/bin/env python3
"""
Runtime profiler for Rule-Bot.
Collects RSS, VMS, VmSwap, CPU%, threads, asyncio tasks, and request metrics.
"""

from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path
from typing import Dict, Optional

import psutil


def read_vmswap_kb(pid: int) -> int:
    status_path = Path(f"/proc/{pid}/status")
    if not status_path.exists():
        return 0
    try:
        with status_path.open("r", encoding="utf-8") as handle:
            for line in handle:
                if line.startswith("VmSwap:"):
                    parts = line.split()
                    if len(parts) >= 2:
                        return int(parts[1])
    except Exception:
        return 0
    return 0


def pick_pid_by_name(name: str) -> Optional[int]:
    candidates = []
    for proc in psutil.process_iter(["pid", "name", "cmdline", "memory_info"]):
        try:
            pname = proc.info.get("name") or ""
            cmdline = " ".join(proc.info.get("cmdline") or [])
            if name in pname or name in cmdline:
                rss = proc.info.get("memory_info").rss if proc.info.get("memory_info") else 0
                candidates.append((rss, proc.info["pid"]))
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    if not candidates:
        return None
    candidates.sort(reverse=True)
    return candidates[0][1]


def load_metrics(path: Path) -> Dict[str, object]:
    if not path.exists():
        return {}
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except Exception:
        return {}


def format_histogram(hist: Dict[str, object]) -> str:
    buckets = hist.get("buckets", [])
    counts = hist.get("counts", [])
    if not buckets or not counts:
        return ""
    parts = []
    for idx, upper in enumerate(buckets):
        parts.append(f"<= {upper}ms: {counts[idx]}")
    parts.append(f"> {buckets[-1]}ms: {counts[-1]}")
    return "; ".join(parts)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pid", type=int, help="Target PID")
    parser.add_argument("--process-name", default="python", help="Process name/cmdline match")
    parser.add_argument("--interval", type=float, default=5.0, help="Sample interval seconds")
    parser.add_argument("--duration", type=float, default=60.0, help="Total duration seconds")
    parser.add_argument("--output", type=Path, help="CSV output path")
    parser.add_argument(
        "--metrics-path",
        type=Path,
        default=Path(os.getenv("METRICS_EXPORT_PATH", "/tmp/rule-bot-metrics.json")),
    )
    args = parser.parse_args()

    pid = args.pid or pick_pid_by_name(args.process_name)
    if not pid:
        print("No process found.")
        return 1

    proc = psutil.Process(pid)
    proc.cpu_percent(interval=None)

    header = [
        "ts",
        "rss_mb",
        "vms_mb",
        "vmswap_mb",
        "cpu_percent",
        "threads",
        "asyncio_tasks",
    ]

    out_handle = None
    if args.output:
        out_handle = args.output.open("w", encoding="utf-8")
        out_handle.write(",".join(header) + "\n")

    start = time.time()
    while time.time() - start <= args.duration:
        time.sleep(args.interval)
        try:
            mem = proc.memory_info()
        except psutil.NoSuchProcess:
            break

        rss_mb = mem.rss / 1024 / 1024
        vms_mb = mem.vms / 1024 / 1024
        swap_mb = read_vmswap_kb(pid) / 1024
        cpu = proc.cpu_percent(interval=None)
        threads = proc.num_threads()

        metrics = load_metrics(args.metrics_path)
        asyncio_tasks = metrics.get("asyncio_task_count", 0)

        ts = time.strftime("%H:%M:%S")
        row = [ts, f"{rss_mb:.1f}", f"{vms_mb:.1f}", f"{swap_mb:.1f}", f"{cpu:.1f}", str(threads), str(asyncio_tasks)]
        line = ",".join(row)
        print(line)
        if out_handle:
            out_handle.write(line + "\n")

    if out_handle:
        out_handle.close()

    metrics = load_metrics(args.metrics_path)
    if metrics:
        print("\n[Metrics Snapshot]")
        counters = metrics.get("counters", {})
        for key, value in sorted(counters.items()):
            print(f"{key}: {value}")
        histograms = metrics.get("histograms", {})
        for key, hist in histograms.items():
            summary = format_histogram(hist)
            if summary:
                print(f"{key}: {summary}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
