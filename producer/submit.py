"""Producer CLI: submit work to NEXUS."""

from __future__ import annotations

import argparse
import json
import sys
import uuid

import httpx


def main() -> None:
    parser = argparse.ArgumentParser(description="Submit work to NEXUS")
    parser.add_argument("--url", default="http://127.0.0.1:8000", help="NEXUS base URL")
    parser.add_argument("--id", help="Work id (default: random uuid)")
    parser.add_argument("--type", default="echo", help="Work type")
    parser.add_argument("--body", default='{"message":"hello"}', help="JSON body")
    parser.add_argument("--count", type=int, default=1, help="Number of work items to submit")
    args = parser.parse_args()

    try:
        body = json.loads(args.body)
    except json.JSONDecodeError as exc:
        print(f"Invalid JSON body: {exc}", file=sys.stderr)
        sys.exit(1)

    base = args.url.rstrip("/")
    submitted = 0

    with httpx.Client(base_url=base, timeout=10.0) as client:
        for i in range(args.count):
            work_id = args.id if args.count == 1 and args.id else f"{args.id or uuid.uuid4()}-{i}"
            if args.count > 1 and args.id:
                work_id = f"{args.id}-{i}"

            payload = {"id": work_id, "type": args.type, "body": body}
            response = client.post("/api/work", json=payload)
            response.raise_for_status()
            work = response.json()
            submitted += 1
            print(f"[{response.status_code}] {work['id']} -> {work['status']}")

    print(f"Submitted {submitted} work item(s) to {base}")


if __name__ == "__main__":
    main()
