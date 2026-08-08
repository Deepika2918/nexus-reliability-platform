"""NEXUS worker process.

Usage:
    python worker/run.py --id worker-1
"""

from __future__ import annotations

import argparse
import time

import requests


def register_worker(server: str, worker_id: str) -> dict:
    response = requests.post(
        f"{server}/api/workers/register",
        json={"id": worker_id},
        timeout=5,
    )
    response.raise_for_status()
    return response.json()


def poll_work(server: str, worker_id: str):
    response = requests.post(
        f"{server}/api/workers/{worker_id}/poll",
        timeout=5,
    )

    if response.status_code == 204:
        return None

    response.raise_for_status()
    return response.json()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--id", default="worker-1")
    parser.add_argument(
        "--server",
        default="http://127.0.0.1:8000",
    )

    args = parser.parse_args()

    print("=" * 50)
    print("NEXUS WORKER")
    print("=" * 50)
    print(f"Worker ID : {args.id}")
    print(f"Server    : {args.server}")
    print()

    try:
        worker = register_worker(args.server, args.id)

        print(f"Worker registered successfully.")
        print(f"Status: {worker['status']}")
        print()
        print("Waiting for work...")
        print("Press CTRL+C to stop.")
        print()

    except requests.RequestException as exc:
        print(f"Could not register worker: {exc}")
        return

    try:
        while True:
            try:
                work = poll_work(args.server, args.id)

                if work is None:
                    print("No work available.")
                    time.sleep(2)
                    continue

                print()
                print("-" * 50)
                print(f"Received work: {work['id']}")
                print(f"Type: {work['type']}")
                print(f"Attempt: {work['attempt_count']}")
                print("-" * 50)

                # For now we only demonstrate dispatch.
                # Completion will be connected after verifying
                # the existing completion API.

                time.sleep(2)

            except requests.RequestException as exc:
                print(f"Worker connection error: {exc}")
                time.sleep(2)

    except KeyboardInterrupt:
        print()
        print("Worker stopped.")


if __name__ == "__main__":
    main()