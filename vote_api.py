"""
MYCELIUM Voting API
Lightweight Flask server that accepts trait votes from visitors and
stores them in generator/votes.json for the next mutation cycle.

Setup:
  pip install flask flask-cors
  python vote_api.py

Nginx proxy block (add inside your mycelium server { } block):
  location /api/ {
      proxy_pass http://127.0.0.1:5000/;
      proxy_set_header Host $host;
      proxy_set_header X-Real-IP $remote_addr;
  }

Run as a systemd service so it starts on boot:
  sudo nano /etc/systemd/system/mycelium-votes.service
  sudo systemctl enable --now mycelium-votes
"""

import json
import os
import time
from datetime import date
from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app, origins="*")

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
GENERATOR_DIR = os.path.join(ROOT_DIR, "generator")
VOTES_FILE = os.path.join(GENERATOR_DIR, "votes.json")

VOTABLE_TRAITS = {
    "mood": [
        "melancholic", "euphoric", "paranoid", "serene", "anxious",
        "nostalgic", "feverish", "detached", "ecstatic", "grieving",
    ],
    "medium": [
        "ascii_art", "svg_geometry", "prose_poetry", "fake_data_viz",
        "glitch_html", "typographic_sculpture", "pseudo_code_poetry",
        "network_diagram", "timeline", "inventory_list",
    ],
    "obsession": [
        "prime_numbers", "forgotten_urls", "color_theory", "sleep_cycles",
        "weather_patterns", "fibonacci", "dead_languages", "radio_frequencies",
        "geological_time", "dream_logic", "bureaucratic_forms", "taxonomy",
    ],
}

# Simple in-memory rate limiting: ip -> [timestamps]
_rate_cache = {}
RATE_WINDOW = 3600  # 1 hour
RATE_MAX = 3        # votes per IP per window


def load_votes():
    os.makedirs(GENERATOR_DIR, exist_ok=True)
    if os.path.exists(VOTES_FILE):
        with open(VOTES_FILE) as f:
            return json.load(f)
    return {"date": str(date.today()), "tallies": {}, "total": 0}


def save_votes(v):
    os.makedirs(GENERATOR_DIR, exist_ok=True)
    with open(VOTES_FILE, "w") as f:
        json.dump(v, f, indent=2)


def is_rate_limited(ip):
    now = time.time()
    timestamps = [t for t in _rate_cache.get(ip, []) if now - t < RATE_WINDOW]
    if len(timestamps) >= RATE_MAX:
        _rate_cache[ip] = timestamps
        return True
    timestamps.append(now)
    _rate_cache[ip] = timestamps
    return False


@app.route("/votes", methods=["GET"])
def get_votes():
    v = load_votes()
    if v.get("date") != str(date.today()):
        v = {"date": str(date.today()), "tallies": {}, "total": 0}
        save_votes(v)
    return jsonify({
        "date": v["date"],
        "tallies": v["tallies"],
        "total": v.get("total", 0),
        "votable_traits": VOTABLE_TRAITS,
    })


@app.route("/vote", methods=["POST"])
def cast_vote():
    ip = request.headers.get("X-Real-IP") or request.remote_addr

    if is_rate_limited(ip):
        return jsonify({"error": "Rate limit reached. You can vote up to 3 times per hour."}), 429

    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Invalid JSON body"}), 400

    trait = data.get("trait")
    value = data.get("value")

    if trait not in VOTABLE_TRAITS:
        return jsonify({"error": f"Unknown trait '{trait}'"}), 400
    if value not in VOTABLE_TRAITS[trait]:
        return jsonify({"error": f"Invalid value '{value}' for trait '{trait}'"}), 400

    v = load_votes()
    if v.get("date") != str(date.today()):
        v = {"date": str(date.today()), "tallies": {}, "total": 0}

    v["tallies"].setdefault(trait, {})[value] = v["tallies"].get(trait, {}).get(value, 0) + 1
    v["total"] = v.get("total", 0) + 1
    save_votes(v)

    return jsonify({
        "ok": True,
        "trait": trait,
        "value": value,
        "new_count": v["tallies"][trait][value],
        "total_votes": v["total"],
    })


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False)
