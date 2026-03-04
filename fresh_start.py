"""
MYCELIUM Fresh Start
Wipes all generated pages, genome state, votes, and history,
then runs backfill to generate a page for every day this month up to today.

Usage:
  python fresh_start.py           # prompts for confirmation
  python fresh_start.py --yes     # skips confirmation
"""

import os
import sys
import json
import shutil
from datetime import date

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
GENERATOR_DIR = os.path.join(ROOT_DIR, "generator")
PAGES_DIR = os.path.join(ROOT_DIR, "pages")
INDEX_FILE = os.path.join(ROOT_DIR, "index.html")

FILES_TO_WIPE = [
    os.path.join(GENERATOR_DIR, "current_genome.json"),
    os.path.join(GENERATOR_DIR, "genome_history.json"),
    os.path.join(GENERATOR_DIR, "pages_metadata.json"),
    os.path.join(GENERATOR_DIR, "votes.json"),
    os.path.join(GENERATOR_DIR, "votes_history.json"),
]


def wipe():
    print("\nWiping state files...")
    for f in FILES_TO_WIPE:
        if os.path.exists(f):
            os.remove(f)
            print(f"  Deleted: {f}")
        else:
            print(f"  Not found (skipping): {f}")

    print("\nWiping generated pages...")
    if os.path.exists(PAGES_DIR):
        count = 0
        for fname in os.listdir(PAGES_DIR):
            if fname.endswith(".html"):
                os.remove(os.path.join(PAGES_DIR, fname))
                count += 1
        print(f"  Deleted {count} page(s)")
    else:
        print("  Pages directory not found, skipping.")

    if os.path.exists(INDEX_FILE):
        os.remove(INDEX_FILE)
        print(f"  Deleted: {INDEX_FILE}")


def run():
    skip_confirm = "--yes" in sys.argv
    today = date.today()

    print(f"\nMYCELIUM Fresh Start")
    print("=" * 40)
    print(f"This will:")
    print(f"  - Delete all generated pages in pages/")
    print(f"  - Wipe all genome, vote, and history JSON files")
    print(f"  - Generate new pages for every day from the 1st of this month up to today ({today})")
    print(f"  - Rebuild the index")
    print()

    if not skip_confirm:
        answer = input("Are you sure? This cannot be undone. [y/N] ").strip().lower()
        if answer != "y":
            print("Aborted.")
            return

    wipe()

    print("\nHanding off to backfill (including today)...")
    # Import and run backfill with today included
    sys.argv = [sys.argv[0], "--yes", "--include-today"]
    import backfill
    backfill.run()


if __name__ == "__main__":
    run()
