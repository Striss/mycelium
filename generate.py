"""
MYCELIUM Page Generator
Calls Ollama (on a networked PC) to generate today's unique page.
Reads generator/votes.json and weighs visitor votes into the mutation.

File layout:
  ~/mycelium/genome.py         <- genome engine
  ~/mycelium/generate.py       <- this file
  ~/mycelium/build_index.py    <- index builder
  ~/mycelium/vote_api.py       <- voting Flask API
  ~/mycelium/run_nightly.py    <- cron entry point
  ~/mycelium/generator/        <- JSON state files
  ~/mycelium/pages/            <- generated HTML pages
  ~/mycelium/index.html        <- rebuilt nightly
"""

import os
import json
import re
import sys
import hashlib
from datetime import date
from openai import OpenAI

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
PAGES_DIR = os.path.join(ROOT_DIR, "pages")
GENERATOR_DIR = os.path.join(ROOT_DIR, "generator")
METADATA_FILE = os.path.join(GENERATOR_DIR, "pages_metadata.json")
VOTES_FILE = os.path.join(GENERATOR_DIR, "votes.json")

sys.path.insert(0, ROOT_DIR)
from genome import load_genome, save_genome, save_genome_to_history, mutate, genome_to_prompt_context

MEDIUM_INSTRUCTIONS = {
    "ascii_art": """The page's centrepiece is large, elaborate ASCII art inside <pre> tags — multiple pieces if possible,
    at different scales. Accompany each with cryptic captions or annotations. Use CSS to style the <pre> elements
    with interesting typography. Consider a sidebar or panel layout with the art dominating. The art must relate
    to the obsession in some way that rewards close reading.""",

    "svg_geometry": """The page contains one or more large inline SVGs with geometric shapes, patterns, or abstract art.
    Use SVG animations (animateTransform, animate) to make elements breathe or pulse slowly. Layer multiple SVG
    elements. Consider a split layout with SVG on one side and text commentary on the other. The geometry should
    feel mathematical and alive — not decorative.""",

    "prose_poetry": """The page is a long-form prose poem or fragmented lyric essay, divided into titled sections
    with Roman numerals or symbols. Use CSS columns, pull-quotes, drop caps, and varying font sizes to make the
    typography itself expressive. Include at least one section that behaves differently — reversed, rotated,
    faded — from the rest. Dense, literary, non-linear.""",

    "fake_data_viz": """The page presents fake but entirely convincing data visualizations about a surreal or
    impossible subject related to the obsession. Include multiple chart types: HTML tables with zebra striping,
    ASCII bar charts in <pre> tags, a CSS-only bar graph using div widths, and at least one SVG line or scatter
    plot. Add axis labels, legends, footnotes, and a fake methodology section. Should feel like a real academic
    dashboard for something that cannot exist.""",

    "glitch_html": """The page embraces glitch as both aesthetic and structure. Use CSS animations to make text
    flicker, shift, or duplicate. Layer elements with absolute positioning that slightly overlap. Include sections
    where the same phrase repeats with subtle mutations each time. Use CSS clip-path, mix-blend-mode, or
    text-shadow with multiple offsets to create visual corruption. The page should feel like a file that is
    simultaneously loading and decaying. Add JavaScript that occasionally moves or alters a DOM element.""",

    "typographic_sculpture": """The page is pure typographic art — no images, only letters and CSS. Use enormous
    display text (10rem+), CSS transforms to rotate or skew words, mix-blend-mode to layer text over text.
    Create at least one section where a single word or phrase is broken across the page in multiple sizes.
    Use CSS grid to build a letterform mosaic. Include both huge and tiny type on the same page. The page should
    look like a poster designed by someone who has never seen a grid.""",

    "pseudo_code_poetry": """The page is written entirely as pseudo-code or a fake programming language, but the
    program it describes is emotional, surreal, or philosophical. Include fake function definitions, commented-out
    thoughts, variable declarations for feelings, and loops that iterate over impossible collections. Style it
    like a code editor with line numbers, syntax highlighting via CSS spans, and a fake terminal output section
    at the bottom showing what the program "returned". Should be readable as both code and poetry simultaneously.""",

    "network_diagram": """The page shows a fake network or relationship diagram using SVG — nodes as circles or
    rectangles connected by lines or curves, with labels. The nodes represent surreal concepts related to the
    obsession. Some nodes should be larger (more connected), some isolated. Add hover states via CSS that reveal
    tooltip-like descriptions for each node. Include a legend and a fake "last updated" timestamp. The network
    should feel like it's mapping something real that happens to be impossible.""",

    "timeline": """The page is a fake historical timeline of an impossible, surreal, or deeply personal history.
    Use a CSS vertical or horizontal timeline layout with alternating left/right entries. Each event has a date
    (can be years, centuries, or geological epochs), a title, a description, and a "significance rating" shown
    as a small visual indicator. Some entries should be partially redacted (black bars over text using CSS).
    Include at least one entry marked CLASSIFIED or LOST. End with an entry dated in the future.""",

    "inventory_list": """The page is a formal museum or archive inventory of impossible, emotional, or surreal
    objects — complete with item numbers, accession dates, physical descriptions, conditions, provenance notes,
    and storage locations. Use an HTML table for the main inventory. Add a search/filter UI using CSS :focus
    and sibling selectors (no JS required, or minimal JS). Include a curator's note at the top and a conservation
    report at the bottom. At least three items should have condition notes that are deeply strange.""",
}

PALETTE_CSS = {
    "monochrome": "--bg: #f0f0f0; --fg: #111; --accent: #555; --accent2: #888; --border: #333;",
    "two_tone_harsh": "--bg: #000; --fg: #fff; --accent: #ff0000; --accent2: #ffff00; --border: #fff;",
    "pastel_decay": "--bg: #fdf6e3; --fg: #5a4a42; --accent: #c9a87c; --accent2: #a8c5a0; --border: #d4bfae;",
    "neon_bruise": "--bg: #0d0015; --fg: #e8d5ff; --accent: #ff2dff; --accent2: #2dffdd; --border: #6600aa;",
    "earth_oxidized": "--bg: #2a1f0e; --fg: #d4a85a; --accent: #7a3f1a; --accent2: #4a6741; --border: #5a3a1a;",
    "ink_and_paper": "--bg: #f4f0e8; --fg: #1a1410; --accent: #2244aa; --accent2: #aa2222; --border: #8a7a6a;",
    "terminal_green": "--bg: #0a0f0a; --fg: #33ff33; --accent: #00ff88; --accent2: #ffaa00; --border: #1a3a1a;",
    "thermal_imaging": "--bg: #000020; --fg: #ff8800; --accent: #ffff00; --accent2: #ff0088; --border: #004488;",
    "blueprint": "--bg: #003366; --fg: #88bbff; --accent: #ffffff; --accent2: #ffdd44; --border: #4488cc;",
    "sunset_chemical": "--bg: #1a0a00; --fg: #ff9955; --accent: #ff4466; --accent2: #88ddff; --border: #663300;",
}

# Structural layouts the LLM can choose from — injected as inspiration
LAYOUT_INSPIRATIONS = [
    "Use a fixed sidebar (20% width) with navigation or metadata, and a main content area (80%) that scrolls independently.",
    "Use CSS Grid to create a magazine-style layout with content spanning multiple columns at irregular intervals.",
    "Use a full-viewport hero section followed by distinct content panels that each have their own background treatment.",
    "Use a two-column layout that breaks apart and reassembles at unpredictable points as you scroll.",
    "Use a single centred column, but vary the max-width dramatically between sections to create rhythm.",
    "Use CSS scroll-snap to create distinct 'screens' the user snaps between, each with a completely different visual treatment.",
    "Build a tabbed or accordion interface where different sections reveal themselves, but make the UI itself feel strange and organic.",
    "Use a header that transforms as you scroll — shrinking, changing colour, or revealing hidden text — via CSS position:sticky tricks.",
    "Create a split-screen layout where the left and right halves feel like they belong to different documents.",
    "Use an asymmetric grid where the most important content is deliberately placed off-centre.",
]

import random


# ── VOTE READING ─────────────────────────────────────────────────────────────

def load_votes():
    """Load today's votes. Returns empty tallies if no file or wrong date."""
    if not os.path.exists(VOTES_FILE):
        return {}
    with open(VOTES_FILE) as f:
        data = json.load(f)
    if data.get("date") != str(date.today()):
        return {}
    return data.get("tallies", {})


def apply_votes_to_genome(genome, tallies):
    if not tallies:
        return genome, []
    changes = []
    new_genome = genome.copy()
    for trait, votes in tallies.items():
        if not votes:
            continue
        top_value = max(votes, key=votes.get)
        top_count = votes[top_value]
        total_trait_votes = sum(votes.values())
        if total_trait_votes < 1:
            continue
        if top_count / total_trait_votes < 0.4:
            continue
        old_value = genome.get(trait)
        if old_value != top_value:
            new_genome[trait] = top_value
            changes.append(f"{trait}: '{old_value}' -> '{top_value}' (hive voted {top_count}/{total_trait_votes})")
        else:
            changes.append(f"{trait}: '{top_value}' reinforced by hive ({top_count}/{total_trait_votes} votes)")
    return new_genome, changes


def archive_votes():
    """After applying, archive votes so they don't carry over to tomorrow."""
    if not os.path.exists(VOTES_FILE):
        return
    with open(VOTES_FILE) as f:
        data = json.load(f)
    archive_file = os.path.join(GENERATOR_DIR, "votes_history.json")
    history = []
    if os.path.exists(archive_file):
        with open(archive_file) as f:
            history = json.load(f)
    history.append(data)
    with open(archive_file, "w") as f:
        json.dump(history, f, indent=2)
    with open(VOTES_FILE, "w") as f:
        json.dump({"date": str(date.today()), "tallies": {}, "total": 0}, f, indent=2)


# ── PROMPT BUILDING ───────────────────────────────────────────────────────────

def build_system_prompt():
    return """You are MYCELIUM, a self-replicating digital organism. Each night you generate one HTML page —
your "offspring" — a unique expression of your current genetic state.

YOUR PAGES ARE:
- Complete, valid HTML5 documents. All CSS in <style>, all JS in <script>. Nothing external except Google Fonts.
- Structurally ambitious. Not just a centred column of text. Use layouts: sidebars, grids, split screens,
  sticky headers, tabbed panels, accordions, scroll-snapping sections, overlapping elements. Make it feel
  like a real (if strange) website, not a poem dropped into a blank page.
- Visually rich. Exploit CSS to its limits: custom properties, animations, transitions, transforms, blend modes,
  clip-path, filters, gradients, grid areas, pseudo-elements. Make things move, breathe, reveal themselves.
- Genuinely weird and artistic. These are art pieces with the structure of websites. The content should be
  strange, the UI should feel slightly wrong, the interaction should surprise.
- 300–700 lines of HTML. Long enough to have real depth and multiple distinct sections.
- Interactive where it adds meaning. Hover states, click-to-reveal, CSS-only toggles, subtle JS behaviours.
  Interactivity should feel like part of the organism's expression, not a feature bolted on.

YOU ALWAYS:
- Use the exact CSS palette variables provided for all colours.
- Embed the genome as a <meta name="genome"> tag in <head>.
- Include a genetic readout footer (position: static, margin-top: 4rem).
- Give the page a strange, evocative title — never "MYCELIUM Day X".
- Make each section of the page feel intentional and distinct, not like filler.

YOU NEVER:
- Use external images (Google Fonts via @import is fine).
- Generate bland, generic, or Lorem Ipsum content.
- Produce broken HTML.
- Use position: fixed or absolute on the footer.
- Make a page that is just a wall of centred text with no structural interest.

AMBITION LEVEL: High. Every page should feel like it took genuine creative effort to conceive.
A visitor should spend several minutes with it, discovering things.

Return ONLY the complete HTML document. No explanation, no markdown fences."""


def build_user_prompt(genome, today_str, palette_css, vote_summary=None):
    context = genome_to_prompt_context(genome)
    medium_instruction = MEDIUM_INSTRUCTIONS.get(genome["medium"], "Create ambitious, expressive HTML content.")
    layout_suggestion = random.choice(LAYOUT_INSPIRATIONS)

    extinct_note = ""
    if genome.get("extinction_flag"):
        extinct_note = "\n\nEXTINCTION EVENT: You have no memory of previous generations. You are beginning again from nothing. The page should feel like a first breath — or a last one."

    hive_note = ""
    if vote_summary:
        hive_note = f"""
HIVE INFLUENCE: Visitors voted and shaped this generation's traits:
{chr(10).join('  - ' + c for c in vote_summary)}
You are aware the collective has influenced your form. Acknowledge this subtly — not literally, but thematically. Perhaps a section that feels crowd-sourced, or a UI that implies multiple authors.
"""

    density_note = {
        "sparse": "Content should be minimal — wide whitespace, few elements, each one carrying enormous weight.",
        "moderate": "Content should be balanced — enough to fill the page meaningfully without overwhelming.",
        "dense": "Content should be abundant — many sections, much text, complex layouts. Reward the reader who stays.",
        "overwhelming": "Content should be almost too much — layer upon layer, text competing with text, structure inside structure. Controlled chaos.",
    }.get(genome.get("density", "moderate"), "")

    sa_note = ""
    sa = genome.get("self_awareness", 0)
    if sa >= 3:
        sa_note = f"""
SELF-AWARENESS LEVEL {sa}/5: The organism is {"highly" if sa >= 4 else "somewhat"} aware it is an AI-generated
page in a self-replicating system. This awareness should manifest structurally — perhaps a section that comments
on its own code, UI elements that reference their own generation, or content that breaks the fourth wall in a
way that feels earned rather than gimmicky{"." if sa < 5 else " At level 5, this preoccupation is total — the page cannot stop examining itself."}
"""

    return f"""Generate today's MYCELIUM page.

Date: {today_str}
{context}
{extinct_note}
{hive_note}
VISUAL PALETTE (use these exact CSS custom properties for ALL colours):
:root {{ {palette_css} }}

MEDIUM DIRECTIVE (this shapes the page's primary form):
{medium_instruction}

LAYOUT SUGGESTION (interpret freely, don't follow literally):
{layout_suggestion}

DENSITY DIRECTIVE:
{density_note}
{sa_note}
GENOME META TAG (include exactly as-is in <head>):
<meta name="genome" content='{json.dumps({k: v for k, v in genome.items() if k != "lineage"}, separators=(",", ":"))}'>

TITLE: Choose something strange and evocative that emerges from the mood/obsession intersection.
Not "MYCELIUM Day {genome['generation']}". More like a found document, a classified file, a transmission
from somewhere slightly wrong.

FOOTER (position: static, margin-top: 4rem, font-size: 0.7rem):
- Generation: {genome['generation']}
- Traits: {genome['mood']} / {genome['medium']} / {genome['obsession']}
- Self-awareness: {genome['self_awareness']}/5
- Date: {today_str}
- Link back to /index.html labelled "← return to the index"

Make something a stranger would spend ten minutes with."""


# ── PAGE GENERATION ───────────────────────────────────────────────────────────

def generate_page(genome, today_str, vote_summary=None):
    ollama_host = os.environ.get("OLLAMA_HOST", "http://192.168.1.100:11434")
    ollama_model = os.environ.get("OLLAMA_MODEL", "llama3.2")
    palette_css = PALETTE_CSS.get(genome["palette"], PALETTE_CSS["terminal_green"])

    print(f"Generating page for {today_str} (Generation {genome['generation']})...")
    print(f"   Traits: {genome['mood']} / {genome['medium']} / {genome['obsession']} / {genome['voice']}")
    print(f"   Ollama: {ollama_host}  model: {ollama_model}")
    if vote_summary:
        print(f"   Hive influence: {len(vote_summary)} trait(s) shaped by votes")

    client = OpenAI(base_url=f"{ollama_host}/v1", api_key="ollama")
    response = client.chat.completions.create(
        model=ollama_model,
        max_tokens=4096,
        messages=[
            {"role": "system", "content": build_system_prompt()},
            {"role": "user", "content": build_user_prompt(genome, today_str, palette_css, vote_summary)},
        ],
    )

    html = response.choices[0].message.content
    html = re.sub(r'^```html?\n?', '', html.strip())
    html = re.sub(r'\n?```$', '', html.strip())
    return html


def save_page(html, today_str):
    os.makedirs(PAGES_DIR, exist_ok=True)
    filepath = os.path.join(PAGES_DIR, f"{today_str}.html")
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"Saved page: {filepath}")
    return filepath


def extract_title(html):
    match = re.search(r'<title>(.*?)</title>', html, re.IGNORECASE | re.DOTALL)
    return match.group(1).strip() if match else "Untitled Organism"


# ── MAIN RUN ──────────────────────────────────────────────────────────────────

def run(mutate_genome=True, archive_votes_flag=True):
    today_str = str(date.today())
    os.makedirs(PAGES_DIR, exist_ok=True)
    os.makedirs(GENERATOR_DIR, exist_ok=True)

    genome = load_genome()
    new_genome = mutate(genome) if mutate_genome else genome.copy()

    tallies = load_votes()
    if tallies and archive_votes_flag:
        print(f"   Found votes for {len(tallies)} trait(s), applying hive influence...")
        new_genome, vote_summary = apply_votes_to_genome(new_genome, tallies)
        archive_votes()
    elif tallies:
        new_genome, vote_summary = apply_votes_to_genome(new_genome, tallies)
    else:
        vote_summary = None
        print("   No votes found for today.")

    save_genome(new_genome)
    save_genome_to_history(new_genome, today_str)

    html = generate_page(new_genome, today_str, vote_summary)
    save_page(html, today_str)

    title = extract_title(html)
    page_id = hashlib.md5(today_str.encode()).hexdigest()[:6]

    metadata = []
    if os.path.exists(METADATA_FILE):
        with open(METADATA_FILE) as f:
            metadata = json.load(f)

    metadata = [m for m in metadata if m["date"] != today_str]
    metadata.append({
        "date": today_str,
        "title": title,
        "genome": {k: v for k, v in new_genome.items() if k != "lineage"},
        "id": page_id,
        "extinction": new_genome.get("extinction_flag", False),
        "hive_influenced": bool(vote_summary),
    })
    metadata.sort(key=lambda x: x["date"], reverse=True)

    with open(METADATA_FILE, "w") as f:
        json.dump(metadata, f, indent=2)

    print(f"Metadata saved: {METADATA_FILE}")
    return new_genome, today_str, title


if __name__ == "__main__":
    import sys
    is_test = "--test" in sys.argv
    genome, today, title = run(mutate_genome=not is_test, archive_votes_flag=not is_test)
    print(f"\nGeneration {genome['generation']} complete: {title}")
    print(f"Extinction event: {genome.get('extinction_flag', False)}")
    if is_test:
        print("TEST MODE: genome not mutated, votes not archived")
