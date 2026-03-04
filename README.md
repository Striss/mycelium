# 🧬 MYCELIUM

**A self-replicating digital organism running on a Raspberry Pi.**

Every night, the organism mutates its genetic code and generates a completely new HTML page — a unique aesthetic artifact shaped by its evolving traits. Watch its personality drift over days, weeks, and months.

---

## Structure

```
mycelium/
├── run_nightly.py              ← Cron calls this
├── requirements.txt
├── generator/
│   ├── genome.py               ← Trait system + mutation engine
│   ├── generate.py             ← Calls Claude API → writes page HTML
│   ├── build_index.py          ← Rebuilds index.html
│   ├── current_genome.json     ← Live genome state (auto-created)
│   ├── genome_history.json     ← Full genome log (auto-created)
│   └── pages_metadata.json     ← Page index data (auto-created)
├── pages/
│   ├── 2025-01-01.html         ← Generated pages live here
│   └── ...
├── logs/
│   └── nightly.log
└── index.html                  ← Auto-rebuilt each night
```

---

## Setup

### 1. Install dependencies

```bash
cd mycelium
pip3 install -r requirements.txt
```

### 2. Set your Anthropic API key

```bash
export ANTHROPIC_API_KEY="sk-ant-..."
# Add to ~/.bashrc or ~/.profile to persist
```

### 3. Run manually for the first time

```bash
python3 run_nightly.py
```

This will:
- Create `generator/current_genome.json` (the organism's DNA)
- Call the Claude API to generate `pages/YYYY-MM-DD.html`
- Rebuild `index.html`

### 4. Serve with your existing web server

Point your server's document root at the `mycelium/` folder.

**Nginx example:**
```nginx
server {
    listen 80;
    server_name your-pi.local;
    root /home/pi/mycelium;
    index index.html;
    location / {
        try_files $uri $uri/ =404;
    }
}
```

### 5. Set up cron for nightly generation

```bash
crontab -e
```

Add this line (runs at 2:00 AM daily):
```
0 2 * * * ANTHROPIC_API_KEY=sk-ant-YOUR-KEY /usr/bin/python3 /home/pi/mycelium/run_nightly.py >> /home/pi/mycelium/logs/nightly.log 2>&1
```

---

## The Genome System

Each page has a **genome** — a JSON object with evolving traits:

| Trait | What it controls |
|-------|-----------------|
| `mood` | Emotional register of the content |
| `medium` | Format/style (ASCII art, SVG, poetry, fake data viz, etc.) |
| `obsession` | The subject matter (primes, sleep cycles, dead languages...) |
| `voice` | Writing style (academic, cryptic, bureaucratic...) |
| `palette` | Visual color scheme |
| `density` | How much content is on the page |
| `self_awareness` | 0-5: how much the page knows it's generated |
| `generation` | Increments each day |

Each night, traits mutate at different rates:
- `mood` changes 35% of nights
- `voice` changes only 15% of nights (very stable)
- `self_awareness` drifts ±1 point at 10% rate

### Extinction Events

On the **1st of each month**, the genome resets completely — all traits randomize. The page that day will reference this as an extinction event.

---

## Manual Controls

```bash
# Regenerate today's page (same genome, new content)
python3 generator/generate.py

# Just rebuild the index (no API call)
python3 generator/build_index.py

# Inspect current genome
python3 generator/genome.py

# Preview a mutation
python3 generator/genome.py --mutate
```

---

## Troubleshooting

**No pages show up:** Run `python3 run_nightly.py` manually and check for errors.

**API errors:** Verify `ANTHROPIC_API_KEY` is set: `echo $ANTHROPIC_API_KEY`

**Cron not running:** Check `logs/nightly.log`. Make sure the API key is exported in the cron line itself (cron doesn't inherit shell env vars).

**Costs:** Each page generation uses ~1,500-3,000 output tokens with Claude Opus. Budget accordingly (~$0.02-0.05 per page at current pricing).
