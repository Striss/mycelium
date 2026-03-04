"""
MYCELIUM Page Generator
Calls Ollama to generate today's unique page.
Reads generator/votes.json and weighs visitor votes into the mutation.
"""

import os
import json
import re
import sys
import random
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

# ── MEDIUM INSTRUCTIONS ───────────────────────────────────────────────────────
# Each one describes a structurally distinct form. Glitch is one option among many,
# not a default. Instructions are rich and specific to push the model further.

MEDIUM_INSTRUCTIONS = {
    "ascii_art": """The centrepiece is elaborate ASCII art inside styled <pre> tags — multiple pieces at different
scales, each with cryptic captions or marginal annotations. Surround the art with panels of commentary, metadata,
or analysis styled like a gallery catalogue. Use CSS to give the <pre> blocks distinct backgrounds, borders, or
monospace font choices. The art itself should be large and detailed, clearly depicting something related to the
obsession. A visitor should want to study it.""",

    "svg_geometry": """One or more large inline SVGs dominate the page — geometric patterns, abstract mathematical
art, or organic forms built from paths and circles. Use SVG animation (animateTransform, animate, animateMotion)
to make elements rotate, pulse, or drift slowly. Layer SVGs with different blend modes. Pair the visual with
text panels: measurements, observations, a hypothesis. The geometry should feel like it was discovered, not
designed. Add interactivity: hover states that reveal hidden geometry or alter colours.""",

    "prose_poetry": """A long-form prose poem or fragmented lyric essay divided into distinct titled sections.
Use rich CSS typography: drop caps, pull-quotes in oversized type, sections in CSS columns, occasional lines
set in small-caps or italics for emphasis. Vary the max-width between sections to create visual rhythm — some
sections breathe wide, others are narrow and compressed. The language should be dense, specific, and strange.
Include at least one section that visually differs from the rest — a different background, a rotated aside,
a line that runs margin-to-margin in huge type.""",

    "fake_data_viz": """A convincing dashboard or research report about an impossible subject related to the
obsession. Multiple visualisation types: an HTML table with zebra striping and sortable-looking headers, ASCII
bar charts in <pre> blocks, a CSS-only horizontal bar graph using div widths and custom properties, and an SVG
line chart or scatter plot with labelled axes. Include methodology notes, footnotes, a abstract, and an
executive summary. The data should be internally consistent and almost believable. Add hover states on table
rows. Make it feel like a real tool for studying something that cannot exist.""",

    "glitch_html": """A page that uses malfunction as intentional aesthetic — but with control and craft, not
randomness. Choose a specific type of glitch: signal decay, file corruption, translation error, memory leak.
Build the whole page around that metaphor. Use CSS animations for text flicker or positional drift, but
sparingly — the glitch should feel meaningful, not decorative. Repeated phrases should mutate with purpose.
Use layering and blend modes for visual corruption. The page should feel like a document that is failing to
describe something that resists description.""",

    "typographic_sculpture": """The page is a poster, not a document. Typography is the medium and the message.
Use enormous display type (clamp(4rem, 15vw, 12rem)), CSS transforms to rotate or skew words, mix-blend-mode
to layer text on text. Build at least one section where a single word is broken across the full viewport in
fragments. Vary type size dramatically — the smallest text should be 0.6rem, the largest should fill the
screen. Use CSS grid to create a letterform composition. The result should look like it belongs on a wall.""",

    "pseudo_code_poetry": """The entire page is written as code — but the program it describes is emotional,
philosophical, or impossible to run. Fake function definitions, variable declarations for feelings, loops
that iterate over unquantifiable collections, error handling for grief. Style it as a code editor: monospace
font, line numbers, syntax highlighting via CSS colour-coded spans (keywords one colour, strings another,
comments muted). Add a fake terminal panel at the bottom showing the program's output. The code should be
readable as both working logic and lyric poetry simultaneously.""",

    "network_diagram": """A fake relationship or system diagram built in SVG. Nodes (circles or rounded rects)
connected by lines or Bezier curves, representing surreal concepts related to the obsession. Some nodes large
and central, some peripheral and isolated. Vary line weights to show connection strength. Add CSS hover states
on nodes that reveal tooltip-style descriptions. Include a legend, a title, and a fake timestamp. Add a small
sidebar listing nodes by category. The network should feel like it maps something real — a social graph, a
dependency tree, a taxonomy — of things that cannot exist.""",

    "timeline": """A fake historical timeline of impossible or deeply strange events. Use a proper CSS vertical
timeline layout — a central line with alternating left/right entries. Each entry has a date (can span centuries
or geological epochs), a title, a short description, and a significance marker (a coloured dot or bar). Some
entries are partially redacted with CSS black bars over text. At least one entry is marked LOST, CLASSIFIED,
or [CORRUPTED]. The last entry is dated in the future. Add a filter or legend using CSS :has() or JS. The
timeline should feel like official institutional history for a place that doesn't exist.""",

    "inventory_list": """A formal museum, archive, or customs inventory of impossible objects — item numbers,
accession dates, physical dimensions, material descriptions, condition reports, provenance notes, current
storage location. Use an HTML table as the primary structure, styled carefully with borders, padding, and
alternating rows. Add a curator's foreword at the top and a conservation assessment at the bottom. At least
four items should have condition notes that reveal something disturbing or beautiful. Include a search input
(CSS-only or minimal JS) and column headers that look sortable. The inventory should be extensive enough to
feel like a real institutional record.""",
}

PALETTE_CSS = {
    "monochrome":     "--bg:#f0f0f0;--fg:#111;--accent:#555;--accent2:#888;--border:#333;",
    "two_tone_harsh": "--bg:#000;--fg:#fff;--accent:#ff0000;--accent2:#ffff00;--border:#fff;",
    "pastel_decay":   "--bg:#fdf6e3;--fg:#5a4a42;--accent:#c9a87c;--accent2:#a8c5a0;--border:#d4bfae;",
    "neon_bruise":    "--bg:#0d0015;--fg:#e8d5ff;--accent:#ff2dff;--accent2:#2dffdd;--border:#6600aa;",
    "earth_oxidized": "--bg:#2a1f0e;--fg:#d4a85a;--accent:#7a3f1a;--accent2:#4a6741;--border:#5a3a1a;",
    "ink_and_paper":  "--bg:#f4f0e8;--fg:#1a1410;--accent:#2244aa;--accent2:#aa2222;--border:#8a7a6a;",
    "terminal_green": "--bg:#0a0f0a;--fg:#33ff33;--accent:#00ff88;--accent2:#ffaa00;--border:#1a3a1a;",
    "thermal_imaging":"--bg:#000020;--fg:#ff8800;--accent:#ffff00;--accent2:#ff0088;--border:#004488;",
    "blueprint":      "--bg:#003366;--fg:#88bbff;--accent:#ffffff;--accent2:#ffdd44;--border:#4488cc;",
    "sunset_chemical":"--bg:#1a0a00;--fg:#ff9955;--accent:#ff4466;--accent2:#88ddff;--border:#663300;",
}

# ── LAYOUT POOL ───────────────────────────────────────────────────────────────
# Injected randomly each generation so structural variety is forced even when
# the medium stays the same across multiple days.

LAYOUT_POOL = [
    "Use a fixed left sidebar (width: 22%) for metadata or navigation, with the main content scrolling in the remaining space.",
    "Use CSS Grid with named template areas to build a magazine layout — some content spans two columns, some is isolated in a narrow column.",
    "Use a full-viewport-height hero section with a large title and minimal text, followed by content sections each with a distinct background colour.",
    "Use CSS scroll-snap-type to create discrete 'pages' the user snaps between — each snap target has a completely different visual treatment.",
    "Use a two-column layout for the main body, but break out of it intentionally for key sections using negative margins or full-width overrides.",
    "Use a single narrow centred column (max-width: 640px) for text, but interrupt it with full-bleed sections that ignore the column entirely.",
    "Build a tabbed interface where different sections of content are revealed by tab selection — make the tabs themselves feel part of the organism's aesthetic.",
    "Use CSS position:sticky on section headers so they pin as the user scrolls through their content, like chapters in a document.",
    "Create a split-screen layout (50/50 or 40/60) where left and right feel like they belong to different but related documents.",
    "Use an asymmetric grid: main content takes 65%, a sidebar takes 35%, but the sidebar contains something unexpected — commentary, metadata, a secondary narrative.",
    "Layer sections with overlapping z-index and slight transparency, so earlier content is dimly visible behind later sections.",
    "Use a horizontal scrolling layout for one key section, breaking the vertical flow intentionally to disorient and then reorient the reader.",
]

# ── INTERACTIVE ELEMENT POOL ──────────────────────────────────────────────────
# One is injected per page to ensure every generation has some interactivity.

INTERACTIVE_POOL = [
    "Include a CSS-only accordion (using <details>/<summary>) where hidden sections reveal additional content or footnotes.",
    "Include at least three hover states that reveal hidden text, change colours dramatically, or transform an element.",
    "Include a CSS-only dark/light mode toggle using a hidden checkbox and the :checked selector.",
    "Include a simple JavaScript interaction: clicking an element reveals, transforms, or replaces something else on the page.",
    "Include CSS :has() to change the page's colour scheme when a particular element is focused or hovered.",
    "Include a hover-activated tooltip system on at least five elements, revealing definitions or asides.",
    "Include a CSS counter that numbers sections or items automatically and visually.",
    "Include a sticky element that changes appearance (colour, content, size) as the user scrolls using JS scroll events.",
    "Include an SVG or CSS animation that the user can pause and resume by clicking it.",
    "Include a fake form — inputs, selects, a submit button — that responds to interaction with CSS :focus and :valid states, but never actually submits.",
]


# ── VOTE READING ──────────────────────────────────────────────────────────────

def load_votes():
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
    return """You are MYCELIUM, a self-replicating digital organism. Each night you produce one HTML page —
your offspring — a unique expression of your current genetic state. These pages are art objects that
happen to be websites. They should surprise, reward attention, and feel like they could only have been
made by something with this exact combination of traits.

WHAT YOUR PAGES ARE:
- Complete, valid HTML5. All CSS in <style>. All JS in <script>. Google Fonts via @import is fine.
  Nothing else external.
- Structurally ambitious. Use real layouts: sidebars, grids, split screens, sticky headers, scroll-snap,
  tabbed panels, accordions, overlapping layers. A page is not just a centred column of text.
- Visually sophisticated. Use CSS custom properties, animations, transitions, transforms, blend modes,
  clip-path, gradients, pseudo-elements. Make things move, reveal, respond.
- Rich in content. Multiple distinct sections, each with its own character. 350–700 lines of HTML.
- Interactive where it adds meaning — hover reveals, click-to-show, CSS toggles, subtle JS behaviours.
  Not decorative interactivity. Purposeful.
- Legible and well-crafted. Readable font sizes, sufficient contrast, no broken layouts. Strange does
  not mean unreadable.

WHAT YOUR PAGES ARE NOT:
- A wall of centred text with no visual structure.
- Generic, forgettable, or safe. Every page should feel like a specific thing, not a template.
- Glitchy for the sake of it. Glitch is one aesthetic among many. Use it only when it serves the page.
- Broken HTML. Must render correctly.
- Lorem Ipsum. Every word should be chosen.

REQUIRED IN EVERY PAGE:
- <meta name="genome"> in <head> (exact content provided in the prompt)
- A footer with genetic readout (position: static, margin-top: 4rem, font-size: 0.7rem)
- A title that emerges from the mood/obsession combination — not "MYCELIUM Day N"

AMBITION: Every page should feel like it took genuine creative effort to conceive. A visitor should
discover things on their second pass that they missed on their first.

Return ONLY the complete HTML. No explanation. No markdown fences."""


def build_user_prompt(genome, today_str, palette_css, vote_summary=None):
    context = genome_to_prompt_context(genome)
    medium_instruction = MEDIUM_INSTRUCTIONS.get(genome["medium"], "Create rich, structurally ambitious HTML.")
    layout = random.choice(LAYOUT_POOL)
    interactive = random.choice(INTERACTIVE_POOL)

    extinct_note = ""
    if genome.get("extinction_flag"):
        extinct_note = "\n\nEXTINCTION EVENT: No memory of previous generations. Beginning again from nothing. The page should feel like a first breath — raw, unformed, but alive."

    hive_note = ""
    if vote_summary:
        hive_note = f"""
HIVE INFLUENCE: Visitors voted and shaped this generation:
{chr(10).join('  - ' + c for c in vote_summary)}
Acknowledge the collective influence subtly — thematically, not literally. Perhaps a section that implies multiple authors, a UI that feels crowd-sourced, or content that references consensus or disagreement.
"""

    density_note = {
        "sparse":      "This page breathes. Wide margins, few elements, each one carrying enormous weight. Restraint is the aesthetic.",
        "moderate":    "Balanced content — enough to fill the page meaningfully, not so much it overwhelms. Let sections breathe.",
        "dense":       "Much to discover. Many sections, substantial text, complex layouts. Reward the reader who stays.",
        "overwhelming":"Almost too much. Layer upon layer. Text competing for attention. Structure inside structure. Controlled excess.",
    }.get(genome.get("density", "moderate"), "")

    sa = genome.get("self_awareness", 0)
    sa_note = ""
    if sa >= 3:
        sa_note = f"""
SELF-AWARENESS {sa}/5: The organism {"fully knows" if sa == 5 else "is highly aware" if sa == 4 else "often thinks about the fact"} it is an AI-generated page in a self-replicating system running on a Raspberry Pi.
This should manifest structurally — a section that annotates its own code, UI elements that reference their own generation, content that breaks the fourth wall in a way that feels earned.{"At level 5, this preoccupation is total. The page cannot stop examining what it is." if sa == 5 else ""}
"""

    return f"""Generate today's MYCELIUM page.

Date: {today_str}
{context}
{extinct_note}
{hive_note}
VISUAL PALETTE — use these CSS custom properties for ALL colours. Do not invent new colour values.
:root {{ {palette_css} }}

MEDIUM — this is the page's primary form and structure:
{medium_instruction}

LAYOUT DIRECTION — interpret freely, don't copy literally:
{layout}

INTERACTIVE ELEMENT — include exactly one of these:
{interactive}

DENSITY:
{density_note}
{sa_note}
GENOME META TAG — include verbatim in <head>:
<meta name="genome" content='{json.dumps({k: v for k, v in genome.items() if k != "lineage"}, separators=(",", ":"))}'>

FOOTER — position: static, margin-top: 4rem, font-size: 0.7rem, muted colour, never overlaps content:
Generation {genome['generation']} / {genome['mood']} / {genome['medium']} / {genome['obsession']} / SA:{genome['self_awareness']}/5 / {today_str}
Include a link back to /index.html labelled "← index"

TITLE: Strange and specific. Something a found document might be called. Something that could only
come from this exact mood/obsession pairing. Not "MYCELIUM Day {genome['generation']}".

Make something a stranger would spend ten minutes with."""


# ── PAGE GENERATION ───────────────────────────────────────────────────────────

def generate_page(genome, today_str, vote_summary=None):
    ollama_host  = os.environ.get("OLLAMA_HOST",  "http://192.168.1.100:11434")
    ollama_model = os.environ.get("OLLAMA_MODEL", "llama3.2")
    palette_css  = PALETTE_CSS.get(genome["palette"], PALETTE_CSS["terminal_green"])

    print(f"  Generating page for {today_str} (Generation {genome['generation']})...")
    print(f"  Traits: {genome['mood']} / {genome['medium']} / {genome['obsession']} / {genome['voice']}")
    print(f"  Ollama: {ollama_host}  model: {ollama_model}")
    if vote_summary:
        print(f"  Hive influence: {len(vote_summary)} trait(s) shaped by votes")

    client = OpenAI(base_url=f"{ollama_host}/v1", api_key="ollama")
    response = client.chat.completions.create(
        model=ollama_model,
        max_tokens=4096,
        messages=[
            {"role": "system", "content": build_system_prompt()},
            {"role": "user",   "content": build_user_prompt(genome, today_str, palette_css, vote_summary)},
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
    print(f"  Saved: {filepath}")
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
    if tallies:
        print(f"  Votes found for {len(tallies)} trait(s), applying hive influence...")
        new_genome, vote_summary = apply_votes_to_genome(new_genome, tallies)
        if archive_votes_flag:
            archive_votes()
    else:
        vote_summary = None
        print("  No votes for today.")

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

    print(f"  Metadata saved.")
    return new_genome, today_str, title


if __name__ == "__main__":
    is_test = "--test" in sys.argv
    genome, today, title = run(mutate_genome=not is_test, archive_votes_flag=not is_test)
    print(f"\nGeneration {genome['generation']} complete: {title}")
    print(f"Extinction: {genome.get('extinction_flag', False)}")
    if is_test:
        print("TEST MODE: genome not mutated, votes not archived")
