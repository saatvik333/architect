#!/usr/bin/env python3
"""ARCHITECT — check if all services respond to /health.

Usage:
    python scripts/check-health.py
    python scripts/check-health.py --timeout 10
"""

from __future__ import annotations

import argparse
import sys
import time

# Service registry: name -> default URL
SERVICES: dict[str, str] = {
    "api-gateway": "http://localhost:8000",
    "task-graph-engine": "http://localhost:8001",
    "execution-sandbox": "http://localhost:8002",
    "world-state-ledger": "http://localhost:8003",
    "spec-engine": "http://localhost:8004",
    "multi-model-router": "http://localhost:8005",
    "codebase-comprehension": "http://localhost:8006",
    "agent-comm-bus": "http://localhost:8007",
    "knowledge-memory": "http://localhost:8008",
    "economic-governor": "http://localhost:8009",
    "security-immune": "http://localhost:8010",
    "deployment-pipeline": "http://localhost:8011",
    "failure-taxonomy": "http://localhost:8012",
    "human-interface": "http://localhost:8013",
}

# ANSI colors
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
RESET = "\033[0m"
BOLD = "\033[1m"


def check_service(name: str, url: str, timeout: float) -> bool:
    """Check if a service responds to /health with a 2xx status."""
    import urllib.error
    import urllib.request

    health_url = f"{url}/health"
    try:
        req = urllib.request.Request(health_url, method="GET")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return 200 <= resp.status < 300
    except (urllib.error.URLError, OSError, TimeoutError):
        return False


def main() -> int:
    """Run health checks against all services and report results."""
    parser = argparse.ArgumentParser(description="Check ARCHITECT service health")
    parser.add_argument(
        "--timeout",
        type=float,
        default=5.0,
        help="Timeout in seconds for each health check (default: 5)",
    )
    parser.add_argument(
        "--wait",
        type=int,
        default=0,
        help="Wait up to N seconds for all services to become healthy (default: 0, no wait)",
    )
    args = parser.parse_args()

    deadline = time.time() + args.wait if args.wait > 0 else 0

    while True:
        results: dict[str, bool] = {}
        for name, url in SERVICES.items():
            results[name] = check_service(name, url, args.timeout)

        healthy = sum(1 for v in results.values() if v)
        total = len(results)

        if healthy == total or time.time() >= deadline:
            break

        # Still waiting for services
        print(
            f"{YELLOW}Waiting... {healthy}/{total} healthy. Retrying in 2s...{RESET}",
            flush=True,
        )
        time.sleep(2)

    # Print results
    print(f"\n{BOLD}ARCHITECT Service Health Check{RESET}")
    print("=" * 50)

    for name, is_healthy in results.items():
        url = SERVICES[name]
        status = f"{GREEN}HEALTHY{RESET}" if is_healthy else f"{RED}DOWN{RESET}"
        print(f"  {name:<30} {url:<35} {status}")

    print("=" * 50)
    healthy = sum(1 for v in results.values() if v)
    total = len(results)

    if healthy == total:
        print(f"\n{GREEN}{BOLD}All {total} services are healthy.{RESET}\n")
        return 0
    else:
        print(f"\n{RED}{BOLD}{healthy}/{total} services healthy.{RESET}\n")
        return 1


if __name__ == "__main__":
    sys.exit(main())
