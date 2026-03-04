# 🧬 MYCELIUM

**A self-replicating digital organism running on a Raspberry Pi.**

Every night, the organism mutates its genetic code and generates a completely new HTML page — a unique aesthetic artifact shaped by its evolving traits. Watch its personality drift over days, weeks, and months. Visitors can vote to influence tomorrow's mutation. Once a month, an extinction event wipes the genome entirely.

Live at: [mycelium.heyjustingray.com](https://mycelium.heyjustingray.com)

---

## How It Works

A cron job fires at 1:30am every night. It mutates a JSON genome, optionally applies visitor votes, calls a local LLM via Ollama, and saves the resulting HTML page. The index rebuilds itself. No human intervention required.

---

## Structure

```
mycelium/
├── run_nightly.py          ← Cron entry point
├── generate.py             ← Calls Ollama → writes page HTML
├── genome.py               ← Trait system + mutation engine
├── build_index.py          ← Rebuilds index.html
├── vote_api.py             ← Flask API for visitor mutation voting
├── backfill.py             ← Generate pages for missing past days
├── fresh_start.py          ← Wipe everything and start over
├── requirements.txt
├── .venv/                  ← Python virtual environment
├── generator/
│   ├── current_genome.json     ← Live genome state (auto-created)
│   ├── genome_history.json     ← Full genome log (auto-created)
│   ├── pages_metadata.json     ← Page index data (auto-created)
│   ├── votes.json              ← Today's votes (auto-created)
│   └── votes_history.json      ← Archived past votes (auto-created)
├── pages/
│   └── YYYY-MM-DD.html         ← Generated pages
├── logs/
│   └── nightly.log
└── index.html                  ← Auto-rebuilt nightly
```

---

## Architecture

### LLM — Ollama (local, networked)

Page generation uses a **locally hosted LLM via Ollama**, running on a separate PC on the same network. The Raspberry Pi makes API calls to it using the OpenAI-compatible endpoint Ollama exposes. No cloud API, no API key, no cost per generation.

Recommended model: `qwen2.5-coder:32b` (best quality). The 7b works but produces simpler output.

```
Raspberry Pi (nginx + Python) ──→ Ollama PC (192.168.2.218:11434)
```

### Voting API — Flask

A lightweight Flask server runs on `localhost:5000` on the Pi and is proxied through nginx at `/api/`. It stores daily votes in `generator/votes.json`. Votes reset after each nightly generation. Rate-limited to 3 votes per IP per hour.

---

## Setup

### 1. Create a virtual environment and install dependencies

```bash
cd ~/mycelium
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Set up Ollama on a networked machine

Install Ollama on any machine on your local network, pull a model, and make sure it's accessible:

```bash
# On the Ollama machine
ollama pull qwen2.5-coder:32b
OLLAMA_HOST=0.0.0.0 ollama serve
```

Test from the Pi:
```bash
curl http://192.168.x.x:11434/api/tags
```

### 3. Run manually for the first time

```bash
cd ~/mycelium
OLLAMA_HOST=http://192.168.x.x:11434 OLLAMA_MODEL=qwen2.5-coder:32b .venv/bin/python run_nightly.py
```

This will create the genome, call Ollama, generate today's page, and rebuild the index.

### 4. Serve with nginx

Point nginx at the mycelium directory. Because nginx runs as `www-data`, you'll need to grant read access:

```bash
sudo groupadd webshare
sudo usermod -aG webshare www-data
sudo usermod -aG webshare USER
sudo chgrp -R webshare /home/USER/mycelium
sudo chmod -R g+rX /home/USER/mycelium
sudo chmod g+s /home/USER/mycelium
```

nginx config:
```nginx
server {
    listen 80;
    server_name mycelium.domainname.com;
    root /home/USER/mycelium;
    index index.html;

    location / {
        try_files $uri $uri/ =404;
    }

    location /api/ {
        proxy_pass http://127.0.0.1:5000/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

### 5. Set up the voting API as a systemd service

```bash
sudo cp mycelium-votes.service /etc/systemd/system/
sudo systemctl enable --now mycelium-votes
sudo systemctl status mycelium-votes
```

The service file points directly at `.venv/bin/python` and runs as the user.

### 6. Set up cron for nightly generation

```bash
crontab -e
```

Add (runs at 1:30am daily):
```
30 1 * * * cd /home/USER/mycelium && OLLAMA_HOST=http://192.168.2.218:11434 OLLAMA_MODEL=qwen2.5-coder:32b .venv/bin/python run_nightly.py >> logs/nightly.log 2>&1
```

Note: use `cd` rather than absolute paths so relative file resolution works correctly.

---

## The Genome System

Each page has a **genome** — a JSON object with evolving traits:

| Trait | What it controls |
|-------|-----------------|
| `mood` | Emotional register (melancholic, euphoric, paranoid...) |
| `medium` | Page form (ASCII art, SVG geometry, fake data viz, timeline...) |
| `obsession` | Subject matter (prime numbers, dead languages, dream logic...) |
| `voice` | Writing style (academic, cryptic, oracular, confessional...) |
| `palette` | Colour scheme (10 options, terminal to pastel) |
| `density` | Content volume (sparse → overwhelming) |
| `self_awareness` | 0–5: how much the page knows it was generated by AI |
| `generation` | Increments each night, survives extinction events |

Mutation rates per night:
- `mood` — 35%
- `palette` — 30%
- `medium` — 25%
- `density` — 25%
- `obsession` — 20%
- `voice` — 15%
- `self_awareness` — 10% (drifts ±1)

### Extinction Events

On the **1st of each month**, the genome fully resets — all traits randomised, all memory erased. Only the generation counter survives. Pages generated after an extinction are marked with an EXTINCTION badge in the fossil record and the organism's content reflects the reset.

### Hive Influence

Visitors vote daily on mood, medium, and obsession. If a trait gets a clear plurality (>40% of votes), it overrides or reinforces that night's mutation. Pages shaped by votes are marked with a HIVE badge. Votes are archived after use and the tally resets for the next day.

---

## Manual Controls

```bash
# Generate today's page normally
OLLAMA_HOST=http://192.168.x.x:11434 OLLAMA_MODEL=qwen2.5-coder:32b .venv/bin/python run_nightly.py

# Regenerate today's page without mutating the genome or archiving votes
.venv/bin/python generate.py --test

# Rebuild the index without generating a page
.venv/bin/python build_index.py

# Inspect current genome
.venv/bin/python genome.py

# Preview what a mutation would produce
.venv/bin/python genome.py --mutate

# Fill in any missing pages for this month
OLLAMA_HOST=http://192.168.x.x:11434 OLLAMA_MODEL=qwen2.5-coder:32b .venv/bin/python backfill.py

# Fill a specific past month
.venv/bin/python backfill.py --month 2026-02

# Complete reset — wipes everything and backfills from the 1st
.venv/bin/python fresh_start.py
```

### Clearing votes manually

```bash
.venv/bin/python3 -c "
import json
from datetime import date
with open('generator/votes.json', 'w') as f:
    json.dump({'date': str(date.today()), 'tallies': {}, 'total': 0}, f, indent=2)
print('Votes cleared.')
"
```

If the site still shows you as having voted, clear it in the browser console:
```javascript
sessionStorage.removeItem('mycelium_votes')
```

### Resetting the genome without wiping history

```bash
.venv/bin/python3 -c "
import sys; sys.path.insert(0, '.')
from genome import load_genome, save_genome, mutate
import json

genome = load_genome()
fresh = mutate(genome, force_extinction=True)
fresh['generation'] = 0
fresh['lineage'] = []
save_genome(fresh)
print('Reset genome:', json.dumps(fresh, indent=2))
"
```

---

## Index Page Features

- **Genome Interpreter** — translates raw JSON into plain English
- **Next Generation Countdown** — ticks down to 1:30am, shows "◆ growing..." in the final 5 minutes
- **Extinction Countdown** — days/hours until the next monthly reset, turns red the day before
- **Mutation Voting** — three-column panel for mood, medium, obsession with live vote tallies
- **Fossil Record** — archive grid of all past pages with palette-accurate preview cards
- **Badges** — EXTINCTION, HIVE, and BACKFILL markers in the fossil record

---

## Troubleshooting

**No pages show up:** Run `run_nightly.py` manually and check for errors.

**Ollama connection refused:** Make sure Ollama is running with `OLLAMA_HOST=0.0.0.0` on the other machine and that the port is accessible from the Pi. Test with `curl http://192.168.2.218:11434/api/tags`.

**Voting API not responding:** Check `sudo systemctl status mycelium-votes`. Restart with `sudo systemctl restart mycelium-votes`.

**Cron not running:** Check `logs/nightly.log`. Cron doesn't inherit shell environment — all env vars must be set in the cron line itself, or use the `cd &&` form.

**nginx 403 errors:** The `webshare` group setup may be incomplete. Check that `www-data` is in the group and that the mycelium directory has `g+rX` permissions.

**Pages look generic:** Try a larger Ollama model. The 7b models drop complex instructions. `qwen2.5-coder:32b` or `qwen2.5-coder:14b` produce significantly better output.
