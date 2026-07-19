"""
Synthetic data layer for the SENTINEL defence-systems console.

EVERYTHING here is fictional / simulated training data. No real units,
positions, capabilities or classified information. This models a *defensive*
situational-awareness + logistics-readiness picture only.
"""

import os
import random
import sqlite3
import time

DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "console.db")

# --- Static fictional order of battle -------------------------------------
ASSETS = [
    {"id": "AIR-01", "name": "Falcon Sqn A", "branch": "Air",         "type": "Multirole fighter wing", "base": "Sector-N",  "readiness": 92},
    {"id": "AIR-02", "name": "Falcon Sqn B", "branch": "Air",         "type": "Interceptor flight",     "base": "Sector-N",  "readiness": 74},
    {"id": "NAV-01", "name": "TF Meridian",  "branch": "Naval",       "type": "Patrol frigate group",   "base": "Port-E",    "readiness": 88},
    {"id": "NAV-02", "name": "TF Tident",    "branch": "Naval",       "type": "Coastal picket",         "base": "Port-E",    "readiness": 61},
    {"id": "LND-01", "name": "9th Mech Bde", "branch": "Land",        "type": "Mechanized brigade",     "base": "Camp-W",    "readiness": 83},
    {"id": "LND-02", "name": "3rd Recon",    "branch": "Land",        "type": "Recon battalion",        "base": "Camp-W",    "readiness": 79},
    {"id": "ADS-01", "name": "Aegis Ring 1", "branch": "Air Defence", "type": "SAM battery (sim)",       "base": "Sector-C",  "readiness": 95},
    {"id": "ADS-02", "name": "Aegis Ring 2", "branch": "Air Defence", "type": "Short-range AD (sim)",    "base": "Sector-S",  "readiness": 68},
    {"id": "CYB-01", "name": "Cyber Watch",  "branch": "Cyber",       "type": "Network defence cell",   "base": "HQ",        "readiness": 90},
    {"id": "ISR-01", "name": "Skyeye ISR",   "branch": "ISR",         "type": "Surveillance platform",  "base": "Sector-N",  "readiness": 86},
]

_CLASSES = ["Commercial", "Friendly", "Unknown", "Unknown", "Hostile-sim"]


def get_assets(branch=None):
    if branch:
        b = branch.strip().lower()
        return [a for a in ASSETS if a["branch"].lower() == b]
    return list(ASSETS)


def get_asset(asset_id):
    aid = (asset_id or "").strip().upper()
    for a in ASSETS:
        if a["id"] == aid:
            return a
    return None


def get_tracks(min_threat=0):
    """Generate a fresh set of SIMULATED radar tracks. Positions jitter each
    call so the dashboard looks 'live'. Threat is a 0-100 heuristic score."""
    rng = random.Random(int(time.time() // 8))  # rerolls every ~8s
    n = rng.randint(6, 11)
    tracks = []
    for i in range(n):
        klass = rng.choice(_CLASSES)
        base = {"Commercial": 5, "Friendly": 2, "Unknown": 45, "Hostile-sim": 85}[klass]
        threat = max(0, min(100, base + rng.randint(-15, 15)))
        tracks.append({
            "id": f"TRK-{1000 + i}",
            "class": klass,
            "bearing": rng.randint(0, 359),
            "range_km": rng.randint(20, 400),
            "alt_m": rng.choice([0, 0, 1500, 6000, 9000, 11000]),
            "speed_kn": rng.randint(90, 620),
            "threat": threat,
        })
    tracks.sort(key=lambda t: t["threat"], reverse=True)
    return [t for t in tracks if t["threat"] >= min_threat]


def readiness_summary():
    out = {}
    for a in ASSETS:
        out.setdefault(a["branch"], []).append(a["readiness"])
    summary = {b: round(sum(v) / len(v)) for b, v in out.items()}
    overall = round(sum(a["readiness"] for a in ASSETS) / len(ASSETS))
    return {"by_branch": summary, "overall": overall}


def threat_posture():
    """Derive an overall readiness condition from current simulated tracks."""
    tracks = get_tracks()
    high = [t for t in tracks if t["threat"] >= 70]
    med = [t for t in tracks if 40 <= t["threat"] < 70]
    if len(high) >= 2:
        level, code, color = 1, "RC-1 CRITICAL", "#ff4d4d"
    elif high:
        level, code, color = 2, "RC-2 ELEVATED", "#ff9f40"
    elif med:
        level, code, color = 3, "RC-3 GUARDED", "#ffd166"
    else:
        level, code, color = 4, "RC-4 NORMAL", "#4dd4a0"
    return {
        "level": level,
        "code": code,
        "color": color,
        "high_threat_tracks": len(high),
        "medium_threat_tracks": len(med),
        "total_tracks": len(tracks),
    }


# --- Incident log (real persistence, SQLite) ------------------------------
def _conn():
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    return c


def init_db():
    with _conn() as c:
        c.execute(
            """CREATE TABLE IF NOT EXISTS incidents (
                   id INTEGER PRIMARY KEY AUTOINCREMENT,
                   ts INTEGER NOT NULL,
                   title TEXT NOT NULL,
                   severity TEXT NOT NULL,
                   note TEXT
               )"""
        )


def log_incident(title, severity="INFO", note=""):
    sev = (severity or "INFO").upper()
    if sev not in ("INFO", "LOW", "MEDIUM", "HIGH", "CRITICAL"):
        sev = "INFO"
    with _conn() as c:
        cur = c.execute(
            "INSERT INTO incidents (ts, title, severity, note) VALUES (?,?,?,?)",
            (int(time.time()), title.strip(), sev, (note or "").strip()),
        )
        return {"id": cur.lastrowid, "title": title, "severity": sev}


def list_incidents(limit=20):
    with _conn() as c:
        rows = c.execute(
            "SELECT * FROM incidents ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
    return [dict(r) for r in rows]
