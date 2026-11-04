#!/usr/bin/env python
"""Run Text-to-SQL model benchmarks through the deployed FastAPI backend."""

import argparse
import json
import sys
from typing import Any, Dict

import requests


def main() -> int:
    parser = argparse.ArgumentParser(description="Benchmark configured Text-to-SQL providers.")
    parser.add_argument("--api-url", default="http://localhost:8000", help="Backend API URL.")
    parser.add_argument("--providers", default="openai,ollama", help="Comma-separated providers: openai,ollama,demo.")
    parser.add_argument("--token", default=None, help="Optional X-LLM-Access-Token value.")
    args = parser.parse_args()

    payload: Dict[str, Any] = {"providers": [provider.strip() for provider in args.providers.split(",") if provider.strip()]}
    headers = {"Content-Type": "application/json"}
    if args.token:
        headers["X-LLM-Access-Token"] = args.token

    response = requests.post(f"{args.api_url.rstrip('/')}/benchmark", json=payload, headers=headers, timeout=300)
    if not response.ok:
        print(f"Benchmark request failed: {response.status_code} {response.text}", file=sys.stderr)
        return 1

    data = response.json()
    print(json.dumps(data, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

