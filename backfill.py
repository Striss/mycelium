"""
MYCELIUM Backfill Script
Generates pages for any days this month that don't yet have one.
Each page is stamped with its actual date so it appears organically born then.
Mutations chain day-by-day so the lineage stays coherent.

Usage:
  python backfill.py                      # fill gaps up to yesterday, prompt first
  python backfill.py --yes                # skip confirmation
  python backfill.py --include-today      # also generate today's page
  python backfill.py --month 2026-02      # backfill a specific past month
  python backfill.py --yes --include-today
"""

import os
import sys
import json
import hashlib
import re
import random
import subprocess
from datetime import date, timedelta
from openai import OpenAI

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
PAGES_DIR = os.path.join(ROOT_DIR, "pages")
GENERATOR_DIR = os.path.join(ROOT_DIR, "generator")
METADATA_FILE = os.path.join(GENERATOR_DIR, "pages_metadata.json")
GENOME_FILE = os.path.join(GENERATOR_DIR, "current_genome.json")

sys.path.insert(0, ROOT_DIR)
from genome import (
    load_genome, save_genome, save_genome_to_history,
    mutate, DEFAULT_GENOME, TRAITS
)
from generate import (
    build_system_prompt, build_user_prompt, extract_title, PALETTE_CSS
)


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
    pages = set()
    if os.path.exists(PAGES_DIR):
        for fname in os.listdir(PAGES_DIR):
            if fname.endswith(".html") and len(fname) == 15:
                pages.add(fname[:-5])
    return pages


def get_missing_dates(year, month, include_today=False):
    today = date.today()
    cursor = date(year, month, 1)
    end = today if include_today else today - timedelta(days=1)
    if month == 12:
        last_day = date(year + 1, 1, 1) - timedelta(days=1)
    else:
        last_day = date(year, month + 1, 1) - timedelta(days=1)
    end = min(end, last_day)
    if cursor > end:
        return []
    existing = get_existing_dates()
    missing = []
    while cursor <= end:
        if str(cursor) not in existing:
            missing.append(cursor)
        cursor += timedelta(days=1)
    return missing


def fresh_genome_seed(day_date):
    g = DEFAULT_GENOME.copy()
    for trait in ["mood", "medium", "obsession", "voice", "palette", "density"]:
        g[trait] = random.choice(TRAITS[trait])
    g["self_awareness"] = random.choice([0, 1, 1, 2, 2, 3])
    g["generation"] = 0
    g["extinction_flag"] = False
    g["lineage"] = []
    g["born"] = str(day_date)
    return g


def backfill_day(day_date, genome):
    date_str = str(day_date)
    print(f"\n  [{date_str}] Generating...")

    new_genome = mutate(genome)
    new_genome["born"] = date_str  # backdate

    save_genome_to_history(new_genome, date_str)

    palette_css = PALETTE_CSS.get(new_genome["palette"], PALETTE_CSS["terminal_green"])
    ollama_host = os.environ.get("OLLAMA_HOST", "http://192.168.1.100:11434")
    ollama_model = os.environ.get("OLLAMA_MODEL", "llama3.2")

    print(f"             mood={new_genome['mood']} medium={new_genome['medium']} obsession={new_genome['obsession']}")
    print(f"             voice={new_genome['voice']} palette={new_genome['palette']} SA={new_genome['self_awareness']}")

    client = OpenAI(base_url=f"{ollama_host}/v1", api_key="ollama")
    response = client.chat.completions.create(
        model=ollama_model,
        max_tokens=4096,
        messages=[
            {"role": "system", "content": build_system_prompt()},
            {"role": "user",   "content": build_user_prompt(new_genome, date_str, palette_css)},
        ],
    )

    html = response.choices[0].message.content
    html = re.sub(r'^```html?\n?', '', html.strip())
    html = re.sub(r'\n?```$', '', html.strip())

    os.makedirs(PAGES_DIR, exist_ok=True)
    with open(os.path.join(PAGES_DIR, f"{date_str}.html"), "w", encoding="utf-8") as f:
        f.write(html)

    title = extract_title(html)
    page_id = hashlib.md5(date_str.encode()).hexdigest()[:6]
    print(f"             title: {title}")

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
    skip_confirm = "--yes" in sys.argv
    include_today = "--include-today" in sys.argv
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

    missing = get_missing_dates(year, month, include_today=include_today)

    if not missing:
        print("No missing pages found. Nothing to do.")
        return

    print(f"\nWill generate {len(missing)} page(s):")
    for d in missing:
        print(f"  {d}")

    if not skip_confirm:
        answer = input(f"\nProceed? [y/N] ").strip().lower()
        if answer != "y":
            print("Aborted.")
            return

    # Start from existing genome, or seed a fresh one if none exists
    if not os.path.exists(GENOME_FILE):
        print(f"\nNo existing genome — starting from a random seed.")
        genome = fresh_genome_seed(missing[0])
    else:
        genome = load_genome()

    metadata = load_metadata()
    new_entries = []

    for day in missing:
        genome, entry = backfill_day(day, genome)
        new_entries.append(entry)

    # Save final genome as current state
    save_genome(genome)
    print(f"\nCurrent genome updated to generation {genome['generation']}.")

    # Merge into metadata
    backfilled_dates = {e["date"] for e in new_entries}
    metadata = [m for m in metadata if m["date"] not in backfilled_dates]
    metadata.extend(new_entries)
    metadata.sort(key=lambda x: x["date"], reverse=True)
    save_metadata(metadata)
    print(f"Metadata saved.")

    # Rebuild index
    print("\nRebuilding index...")
    result = subprocess.run(
        [sys.executable, os.path.join(ROOT_DIR, "build_index.py")],
        capture_output=True, text=True
    )
    print(result.stdout.strip())
    if result.returncode != 0:
        print("Warning — index errors:")
        print(result.stderr)

    print(f"\nDone. {len(new_entries)} page(s) generated and backdated.")


if __name__ == "__main__":
    run()
