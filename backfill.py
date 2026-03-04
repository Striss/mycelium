"""
MYCELIUM Backfill Script
Generates pages for any days this month that don't yet have one.

Usage:
  python backfill.py              # fills gaps from 1st of month up to yesterday
  python backfill.py --yes        # skip confirmation prompt
  python backfill.py --month 2026-02  # backfill a specific past month

Each missing day gets its own genome mutation (chained from the previous day's
genome so the lineage stays coherent), and the index is rebuilt at the end.

NOTE: Backfilled pages are marked with backfill:true in metadata so you can
distinguish them from organically generated pages in the fossil record.
"""

import os
import sys
import json
import hashlib
import re
from datetime import date, timedelta
from openai import OpenAI

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
PAGES_DIR = os.path.join(ROOT_DIR, "pages")
GENERATOR_DIR = os.path.join(ROOT_DIR, "generator")
METADATA_FILE = os.path.join(GENERATOR_DIR, "pages_metadata.json")

sys.path.insert(0, ROOT_DIR)
from genome import load_genome, save_genome, save_genome_to_history, mutate, genome_to_prompt_context
from generate import generate_page, extract_title, PALETTE_CSS, build_system_prompt, build_user_prompt


def load_metadata():
    if not os.path.exists(METADATA_FILE):
        return []
    with open(METADATA_FILE) as f:
        return json.load(f)


def save_metadata(metadata):
    os.makedirs(GENERATOR_DIR, exist_ok=True)
    with open(METADATA_FILE, "w") as f:
        json.dump(metadata, f, indent=2)


def get_existing_dates():
    """Return set of date strings that already have pages."""
    pages = set()
    if os.path.exists(PAGES_DIR):
        for fname in os.listdir(PAGES_DIR):
            if fname.endswith(".html") and len(fname) == 15:  # YYYY-MM-DD.html
                pages.add(fname[:-5])
    return pages


def get_missing_dates(year, month):
    """Return sorted list of dates in the given month that have no page, up to yesterday."""
    today = date.today()
    # Start from 1st of the given month
    cursor = date(year, month, 1)
    # End at yesterday (don't backfill today — that's the nightly job's territory)
    end = today - timedelta(days=1)

    # If the requested month is in the future, nothing to do
    if cursor > end:
        return []

    # Cap end at last day of the requested month
    if cursor.month == today.month and cursor.year == today.year:
        end = today - timedelta(days=1)
    else:
        # Last day of the requested month
        next_month = date(year + (month // 12), (month % 12) + 1, 1)
        end = min(end, next_month - timedelta(days=1))

    existing = get_existing_dates()
    missing = []
    while cursor <= end:
        if str(cursor) not in existing:
            missing.append(cursor)
        cursor += timedelta(days=1)
    return missing


def backfill_day(day_date, genome):
    """Generate a page for a specific past date using a given genome. Returns updated genome."""
    date_str = str(day_date)
    print(f"\n  Generating {date_str}...")

    # Mutate from the provided genome
    new_genome = mutate(genome)
    # Override generation timestamp context
    save_genome_to_history(new_genome, date_str)

    # Generate the page
    palette_css = PALETTE_CSS.get(new_genome["palette"], PALETTE_CSS["terminal_green"])
    ollama_host = os.environ.get("OLLAMA_HOST", "http://192.168.1.100:11434")
    ollama_model = os.environ.get("OLLAMA_MODEL", "llama3.2")

    print(f"     Traits: {new_genome['mood']} / {new_genome['medium']} / {new_genome['obsession']}")

    client = OpenAI(base_url=f"{ollama_host}/v1", api_key="ollama")
    response = client.chat.completions.create(
        model=ollama_model,
        max_tokens=4096,
        messages=[
            {"role": "system", "content": build_system_prompt()},
            {"role": "user", "content": build_user_prompt(new_genome, date_str, palette_css)},
        ],
    )

    html = response.choices[0].message.content
    html = re.sub(r'^```html?\n?', '', html.strip())
    html = re.sub(r'\n?```$', '', html.strip())

    # Save page
    os.makedirs(PAGES_DIR, exist_ok=True)
    filepath = os.path.join(PAGES_DIR, f"{date_str}.html")
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"     Saved: {filepath}")

    title = extract_title(html)
    page_id = hashlib.md5(date_str.encode()).hexdigest()[:6]

    print(f"     Title: {title}")
    return new_genome, {
        "date": date_str,
        "title": title,
        "genome": {k: v for k, v in new_genome.items() if k != "lineage"},
        "id": page_id,
        "extinction": new_genome.get("extinction_flag", False),
        "hive_influenced": False,
        "backfill": True,
    }


def run():
    # Parse args
    skip_confirm = "--yes" in sys.argv
    target_month = None
    if "--month" in sys.argv:
        idx = sys.argv.index("--month")
        try:
            parts = sys.argv[idx + 1].split("-")
            target_month = (int(parts[0]), int(parts[1]))
        except (IndexError, ValueError):
            print("Invalid --month format. Use: --month YYYY-MM")
            sys.exit(1)

    today = date.today()
    year, month = target_month if target_month else (today.year, today.month)

    print(f"\nMYCELIUM Backfill — {year}-{month:02d}")
    print("=" * 40)

    missing = get_missing_dates(year, month)

    if not missing:
        print("No missing pages found. Nothing to do.")
        return

    print(f"\nMissing pages ({len(missing)}):")
    for d in missing:
        print(f"  {d}")

    if not skip_confirm:
        answer = input(f"\nGenerate {len(missing)} page(s)? [y/N] ").strip().lower()
        if answer != "y":
            print("Aborted.")
            return

    # Load current genome as starting point for the chain
    genome = load_genome()
    metadata = load_metadata()

    new_entries = []
    for day in missing:
        genome, entry = backfill_day(day, genome)
        new_entries.append(entry)

    # Merge into metadata (remove any existing entries for these dates, then add new ones)
    backfilled_dates = {e["date"] for e in new_entries}
    metadata = [m for m in metadata if m["date"] not in backfilled_dates]
    metadata.extend(new_entries)
    metadata.sort(key=lambda x: x["date"], reverse=True)
    save_metadata(metadata)

    print(f"\nMetadata updated: {METADATA_FILE}")

    # Rebuild index
    print("\nRebuilding index...")
    import subprocess
    result = subprocess.run(
        [sys.executable, os.path.join(ROOT_DIR, "build_index.py")],
        capture_output=True, text=True
    )
    print(result.stdout.strip())
    if result.returncode != 0:
        print("Warning: index rebuild had errors:")
        print(result.stderr.strip())

    print(f"\nDone. {len(new_entries)} page(s) generated.")
    print("Backfilled pages are marked with a BACKFILL badge in the fossil record.")


if __name__ == "__main__":
    run()
