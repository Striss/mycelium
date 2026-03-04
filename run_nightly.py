#!/usr/bin/env python3
"""
MYCELIUM Nightly Runner
This is the script your cron job calls.

Cron setup (runs at 2:00 AM daily):
  0 2 * * * /usr/bin/python3 /path/to/mycelium/run_nightly.py >> /path/to/mycelium/logs/nightly.log 2>&1
"""

import sys
import os
import traceback
from datetime import datetime

# Add generator to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "generator"))

LOG_DIR = os.path.join(os.path.dirname(__file__), "logs")
os.makedirs(LOG_DIR, exist_ok=True)


def log(msg):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] {msg}"
    print(line)


def main():
    log("=" * 60)
    log("MYCELIUM NIGHTLY RUN STARTING")
    log("=" * 60)

    # Step 1: Generate today's page
    log("STEP 1: Generating today's page...")
    try:
        import generate
        genome, today_str, title = generate.run()
        log(f"  ✓ Page generated: {title} (Generation {genome['generation']})")
        log(f"  ✓ Traits: {genome['mood']} / {genome['medium']} / {genome['obsession']}")
        if genome.get("extinction_flag"):
            log("  ☄ EXTINCTION EVENT OCCURRED")
    except Exception as e:
        log(f"  ✗ Page generation FAILED: {e}")
        traceback.print_exc()
        return 1

    # Step 2: Rebuild index
    log("STEP 2: Rebuilding index.html...")
    try:
        import build_index
        build_index.run()
        log("  ✓ Index rebuilt")
    except Exception as e:
        log(f"  ✗ Index rebuild FAILED: {e}")
        traceback.print_exc()
        return 1

    log("=" * 60)
    log("MYCELIUM NIGHTLY RUN COMPLETE")
    log("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
