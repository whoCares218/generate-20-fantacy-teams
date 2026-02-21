# ============================================================
# FantasyXI — Fantasy Cricket Team Generator
# Flask single-file app | ICC T20 World Cup 2026 Super 8s
#
# JSON schema:
#   teams.json   → teams[].team (name), no team_id
#   matches.json → matches[].team1 / .team2 (name strings), .venue
# ============================================================

import json, random, hashlib, io
from flask import Flask, render_template_string, request, jsonify, send_file, session
from collections import defaultdict

app = Flask(__name__)
app.secret_key = "fantasyxi_super8_2026"

# ─── Data ─────────────────────────────────────────────────────────────────────

def load_teams():
    with open("teams.json") as f: return json.load(f)

def load_matches():
    with open("matches.json") as f: return json.load(f)

def teams_by_name():
    return {t["team"]: t for t in load_teams()["teams"]}

def get_players(team_name):
    t = teams_by_name().get(team_name)
    if not t: return [], [], team_name
    ps = t["players"]
    return ps[:11], ps[11:], t["team"]

# ─── Generation Engine ─────────────────────────────────────────────────────────

def hash_team(ids):
    return hashlib.md5(",".join(sorted(ids)).encode()).hexdigest()

def risk_w(p, mode):
    r = p.get("risk_level", "Medium")
    return {"safe": {"Low":5,"Medium":2,"High":0.4},
            "balanced": {"Low":3,"Medium":3,"High":1.5},
            "risky": {"Low":1.5,"Medium":2.5,"High":5}}[mode][r]

def roles_ok(players):
    roles = [p["role"] for p in players]
    wk = roles.count("Wicketkeeper-Batsman")
    bat = roles.count("Batsman")
    ar = roles.count("All-rounder")
    bowl = roles.count("Bowler")
    return (1<=wk<=4) and (3<=bat<=6) and (1<=ar<=4) and (3<=bowl<=6)

def gen_teams(team1, team2, mode, cr, mn, mx, nt=20):
    xi1, bench1, _ = get_players(team1)
    xi2, bench2, _ = get_players(team2)

    if mode == "safe":
        pool1, pool2 = xi1[:], xi2[:]
    elif mode == "balanced":
        pool1 = xi1[:] + bench1[:2]
        pool2 = xi2[:] + bench2[:2]
    else:
        pool1 = xi1[:] + bench1[:]
        pool2 = xi2[:] + bench2[:]

    appear = defaultdict(int)
    cap_cnt = defaultdict(int)
    vc_cnt = defaultdict(int)
    cv_pairs = set()
    th_set = set()
    last_cap = []
    result = []

    def cap_pool(players):
        if mode == "safe":
            e = [p for p in players if p["risk_level"] == "Low"]
        elif mode == "balanced":
            e = [p for p in players if p["risk_level"] in ("Low","Medium")]
        else:
            e = players[:]
        return e or players[:]

    def pick_unique(pool, weights, n):
        seen, out = [], []
        tries = random.choices(pool, weights=weights, k=min(len(pool), n*4))
        for p in tries:
            if p["id"] not in seen:
                seen.append(p["id"]); out.append(p)
            if len(out) == n: break
        rest = [p for p in pool if p["id"] not in seen]
        random.shuffle(rest)
        for p in rest:
            if len(out) == n: break
            out.append(p); seen.append(p["id"])
        return out

    for idx in range(nt):
        valid = False; attempts = 0
        captain = vice_captain = None
        sel1 = sel2 = []

        while not valid and attempts < 300:
            attempts += 1
            n1, n2 = (6,5) if (cr.get("c1",True) and idx%2==0) else (5,6)
            w1 = [risk_w(p,mode) for p in pool1]
            w2 = [risk_w(p,mode) for p in pool2]
            sel1 = pick_unique(pool1, w1, n1)
            sel2 = pick_unique(pool2, w2, n2)
            if len(sel1) != n1 or len(sel2) != n2: continue
            players = sel1 + sel2

            if cr.get("c14",True) and not roles_ok(players): continue
            if cr.get("c13",True) and (len(sel1)>7 or len(sel2)>7): continue
            if mode=="safe" and sum(1 for p in players if p["risk_level"]=="High")>4: continue
            if mode=="risky" and cr.get("c10",True):
                if sum(1 for p in players if p["role"]=="All-rounder")<3 and attempts<150: continue

            h = hash_team([p["id"] for p in players])
            if cr.get("c12",True) and h in th_set: continue

            cp = cap_pool(players)
            def cw(p):
                b = risk_w(p, mode); b /= (1 + cap_cnt[p["id"]] * 0.5); return max(b, 0.05)
            cws = [cw(p) for p in cp]

            if cr.get("c11",True) and len(last_cap)>=3 and len(set(last_cap[-3:]))==1:
                forb = last_cap[-3]
                alt = [(p,w) for p,w in zip(cp,cws) if p["id"]!=forb]
                if alt: cp, cws = zip(*alt); cp, cws = list(cp), list(cws)

            captain = random.choices(cp, weights=cws, k=1)[0]

            if cr.get("c15",True) and idx<5:
                ar_capped = any(any(p["id"]==cid and p["role"]=="All-rounder" for p in players) for cid in cap_cnt)
                if not ar_capped and idx==4:
                    arc = [p for p in cp if p["role"]=="All-rounder"]
                    if arc: captain = random.choice(arc)

            vp = [p for p in players if p["id"] != captain["id"]]
            if not vp: continue
            def vw(p):
                b = risk_w(p, mode); b /= (1 + vc_cnt[p["id"]] * 0.3); return max(b, 0.05)
            vws = [vw(p) for p in vp]

            if cr.get("c7",True):
                alt = [(p,w) for p,w in zip(vp,vws) if (captain["id"],p["id"]) not in cv_pairs]
                if alt: vp, vws = zip(*alt); vp, vws = list(vp), list(vws)

            vice_captain = random.choices(vp, weights=vws, k=1)[0]
            cv = (captain["id"], vice_captain["id"])

            if cr.get("c6",True) and len(cv_pairs)<5 and len(result)>=5:
                if cv in cv_pairs and attempts<150: continue

            valid = True
            th_set.add(h); cv_pairs.add(cv)
            cap_cnt[captain["id"]] += 1; vc_cnt[vice_captain["id"]] += 1
            last_cap.append(captain["id"])
            for p in players: appear[p["id"]] += 1

        result.append({
            "players": (sel1+sel2) if (sel1 or sel2) else [],
            "captain": captain["name"] if captain else "—",
            "vice_captain": vice_captain["name"] if vice_captain else "—",
            "from_t1": len(sel1),
            "from_t2": len(sel2),
        })

    return result, len(cap_cnt), len(cv_pairs)

# ─── Shared CSS (written inline in each template) ─────────────────────────────

_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Bebas+Neue&family=Inter:wght@300;400;500;600;700&display=swap');

:root {
  --bg: #09090f;
  --s1: #0f1018;
  --s2: #14151f;
  --s3: #1a1b28;
  --s4: #20213a;
  --brd: #2a2b45;
  --brd2: #363760;
  --gld: #f5c518;
  --gld2: #d4a800;
  --ora: #ff5f1f;
  --grn: #22c55e;
  --blu: #38bdf8;
  --red: #ef4444;
  --pur: #a78bfa;
  --txt: #e2e8f0;
  --txt2: #94a3b8;
  --txt3: #64748b;
}

*, *::before, *::after { margin: 0; padding: 0; box-sizing: border-box; }
html { scroll-behavior: smooth; }

body {
  font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
  background: var(--bg);
  color: var(--txt);
  min-height: 100vh;
  overflow-x: hidden;
}

/* Grid texture */
body::before {
  content: '';
  position: fixed;
  inset: 0;
  z-index: 0;
  pointer-events: none;
  background-image:
    radial-gradient(ellipse 60% 40% at 50% 0%, rgba(245,197,24,.06) 0%, transparent 70%),
    linear-gradient(rgba(255,255,255,.012) 1px, transparent 1px),
    linear-gradient(90deg, rgba(255,255,255,.012) 1px, transparent 1px);
  background-size: 100% 100%, 44px 44px, 44px 44px;
}

.z1 { position: relative; z-index: 1; }

/* ─ Header ─ */
header {
  position: sticky;
  top: 0;
  z-index: 500;
  background: rgba(9,9,15,.97);
  border-bottom: 1px solid var(--brd);
  backdrop-filter: blur(20px);
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 0 32px;
  height: 62px;
}

.logo {
  font-family: 'Bebas Neue', Impact, sans-serif;
  font-size: 1.9rem;
  letter-spacing: 3px;
  background: linear-gradient(135deg, var(--gld) 20%, var(--ora));
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
  line-height: 1;
}

.logo-sub {
  font-size: 0.62rem;
  color: var(--txt3);
  letter-spacing: 2px;
  text-transform: uppercase;
  margin-top: 2px;
}

nav { margin-left: auto; display: flex; gap: 4px; }

nav a {
  color: var(--txt3);
  text-decoration: none;
  font-size: 0.78rem;
  padding: 6px 14px;
  border-radius: 8px;
  border: 1px solid transparent;
  transition: all .2s;
  font-weight: 500;
}
nav a:hover { border-color: var(--brd2); color: var(--txt); }

/* ─ Page wrap ─ */
.wrap {
  max-width: 1240px;
  margin: 0 auto;
  padding: 32px 20px 80px;
}

/* ─ Hero ─ */
.hero {
  text-align: center;
  padding: 64px 20px 48px;
}

.hero h1 {
  font-family: 'Bebas Neue', Impact, sans-serif;
  font-size: clamp(3rem, 8vw, 6rem);
  letter-spacing: 6px;
  line-height: 0.9;
  background: linear-gradient(160deg, var(--gld) 0%, #ff9500 50%, var(--ora) 100%);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
}

.hero p {
  color: var(--txt2);
  margin-top: 14px;
  font-size: 1rem;
  font-weight: 400;
}

.tournament-pill {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  margin-top: 16px;
  background: rgba(245,197,24,.1);
  border: 1px solid rgba(245,197,24,.3);
  border-radius: 100px;
  padding: 5px 16px;
  font-size: 0.7rem;
  color: var(--gld);
  letter-spacing: 1.5px;
  text-transform: uppercase;
  font-weight: 600;
}

/* ─ Section heading ─ */
.sh {
  font-family: 'Bebas Neue', Impact, sans-serif;
  font-size: 1.4rem;
  letter-spacing: 3px;
  color: var(--gld);
  margin-bottom: 18px;
  display: flex;
  align-items: center;
  gap: 12px;
}
.sh::after {
  content: '';
  flex: 1;
  height: 1px;
  background: linear-gradient(to right, var(--brd), transparent);
}

/* ─ Tabs ─ */
.tab-bar {
  display: flex;
  gap: 2px;
  background: var(--s1);
  border: 1px solid var(--brd);
  border-radius: 12px;
  padding: 4px;
  width: fit-content;
  margin-bottom: 28px;
}

.tab-btn {
  padding: 8px 22px;
  border-radius: 9px;
  border: none;
  background: transparent;
  color: var(--txt3);
  font-family: 'Inter', sans-serif;
  font-size: 0.82rem;
  font-weight: 500;
  cursor: pointer;
  transition: all .2s;
}

.tab-btn.active {
  background: var(--s3);
  color: var(--txt);
  border: 1px solid var(--brd2);
  box-shadow: 0 2px 8px rgba(0,0,0,.4);
}

/* ─ Match cards ─ */
.match-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  gap: 14px;
  margin-bottom: 36px;
}

.match-card {
  background: var(--s2);
  border: 1px solid var(--brd);
  border-radius: 16px;
  padding: 20px;
  cursor: pointer;
  transition: all .22s ease;
  position: relative;
  overflow: hidden;
}

.match-card::before {
  content: '';
  position: absolute;
  inset: 0;
  background: linear-gradient(135deg, rgba(245,197,24,.05) 0%, transparent 60%);
  opacity: 0;
  transition: opacity .22s;
}

.match-card:hover {
  border-color: rgba(245,197,24,.5);
  transform: translateY(-3px);
  box-shadow: 0 8px 32px rgba(0,0,0,.5);
}
.match-card:hover::before { opacity: 1; }
.match-card.selected {
  border-color: var(--gld);
  background: rgba(245,197,24,.06);
  box-shadow: 0 0 0 1px var(--gld), 0 8px 32px rgba(245,197,24,.1);
}

.match-time-badge {
  position: absolute;
  top: 12px;
  right: 12px;
  background: rgba(245,197,24,.15);
  border: 1px solid rgba(245,197,24,.3);
  color: var(--gld);
  font-size: 0.6rem;
  font-weight: 700;
  padding: 3px 10px;
  border-radius: 100px;
  letter-spacing: 0.5px;
}

.match-id {
  font-size: 0.65rem;
  color: var(--txt3);
  letter-spacing: 1.5px;
  text-transform: uppercase;
  margin-bottom: 10px;
  font-weight: 600;
}

.match-teams {
  font-family: 'Bebas Neue', Impact, sans-serif;
  font-size: 1.8rem;
  letter-spacing: 2px;
  text-align: center;
  line-height: 1;
  color: var(--txt);
}

.match-teams em {
  color: var(--gld);
  font-style: normal;
  font-size: 1rem;
  margin: 0 8px;
  vertical-align: middle;
}

.match-venue {
  text-align: center;
  font-size: 0.68rem;
  color: var(--txt3);
  margin-top: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 4px;
}

/* ─ Mode cards ─ */
.mode-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 14px;
  margin-bottom: 32px;
}

@media (max-width: 580px) { .mode-grid { grid-template-columns: 1fr; } }

.mode-card {
  border-radius: 16px;
  padding: 24px 18px;
  text-align: center;
  cursor: pointer;
  border: 2px solid transparent;
  transition: all .25s ease;
  position: relative;
  overflow: hidden;
}

.mode-card.safe {
  background: linear-gradient(145deg, #071a0e, #0a1a0e);
  border-color: rgba(34,197,94,.3);
}
.mode-card.balanced {
  background: linear-gradient(145deg, #071020, #0a1525);
  border-color: rgba(56,189,248,.3);
}
.mode-card.risky {
  background: linear-gradient(145deg, #1a0707, #1f0a0a);
  border-color: rgba(239,68,68,.3);
}

.mode-card:hover { transform: translateY(-4px); }

.mode-card.active.safe {
  border-color: var(--grn);
  box-shadow: 0 0 30px rgba(34,197,94,.2), inset 0 0 30px rgba(34,197,94,.04);
}
.mode-card.active.balanced {
  border-color: var(--blu);
  box-shadow: 0 0 30px rgba(56,189,248,.2), inset 0 0 30px rgba(56,189,248,.04);
}
.mode-card.active.risky {
  border-color: var(--red);
  box-shadow: 0 0 30px rgba(239,68,68,.2), inset 0 0 30px rgba(239,68,68,.04);
}

.mode-icon { font-size: 2.5rem; margin-bottom: 10px; }

.mode-name {
  font-family: 'Bebas Neue', Impact, sans-serif;
  font-size: 1.6rem;
  letter-spacing: 3px;
}
.mode-card.safe .mode-name { color: var(--grn); }
.mode-card.balanced .mode-name { color: var(--blu); }
.mode-card.risky .mode-name { color: var(--red); }

.mode-desc {
  font-size: 0.73rem;
  color: var(--txt3);
  margin-top: 6px;
  line-height: 1.5;
}

/* ─ Criteria ─ */
.crit-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(255px, 1fr));
  gap: 8px;
  margin-bottom: 28px;
}

.crit-item {
  background: var(--s2);
  border: 1px solid var(--brd);
  border-radius: 10px;
  padding: 11px 14px;
  display: flex;
  align-items: center;
  gap: 10px;
  cursor: pointer;
  transition: border-color .18s;
}
.crit-item:hover { border-color: rgba(245,197,24,.4); }
.crit-item input[type="checkbox"] {
  accent-color: var(--gld);
  width: 15px;
  height: 15px;
  flex-shrink: 0;
  cursor: pointer;
}
.crit-item label {
  font-size: 0.76rem;
  color: var(--txt);
  cursor: pointer;
  line-height: 1.3;
}

/* ─ Inputs ─ */
.input-row {
  display: flex;
  gap: 16px;
  flex-wrap: wrap;
  margin-bottom: 24px;
}

.input-group {
  flex: 1;
  min-width: 150px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.input-group label {
  font-size: 0.68rem;
  color: var(--txt3);
  letter-spacing: 1px;
  text-transform: uppercase;
  font-weight: 600;
}

.input-group input,
.input-group select {
  background: var(--s2);
  border: 1px solid var(--brd);
  border-radius: 9px;
  padding: 9px 13px;
  color: var(--txt);
  font-size: 0.88rem;
  font-family: 'Inter', sans-serif;
  width: 100%;
  transition: border-color .18s;
  outline: none;
}

.input-group input:focus,
.input-group select:focus {
  border-color: rgba(245,197,24,.6);
  box-shadow: 0 0 0 3px rgba(245,197,24,.08);
}

/* ─ Buttons ─ */
.btn {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 12px 28px;
  border-radius: 10px;
  border: none;
  cursor: pointer;
  font-family: 'Bebas Neue', Impact, sans-serif;
  font-size: 1.1rem;
  letter-spacing: 2px;
  text-decoration: none;
  transition: all .2s ease;
  white-space: nowrap;
}

.btn-gold {
  background: linear-gradient(135deg, var(--gld) 0%, #d4a800 100%);
  color: #000;
}
.btn-gold:hover {
  transform: translateY(-2px);
  box-shadow: 0 8px 24px rgba(245,197,24,.35);
}

.btn-orange {
  background: linear-gradient(135deg, var(--ora) 0%, #e04000 100%);
  color: #fff;
}
.btn-orange:hover {
  transform: translateY(-2px);
  box-shadow: 0 8px 24px rgba(255,95,31,.35);
}

.btn-green {
  background: linear-gradient(135deg, var(--grn) 0%, #16a34a 100%);
  color: #000;
}
.btn-green:hover {
  transform: translateY(-2px);
  box-shadow: 0 8px 24px rgba(34,197,94,.35);
}

.btn-ghost {
  background: transparent;
  color: var(--txt3);
  border: 1px solid var(--brd);
}
.btn-ghost:hover { border-color: var(--brd2); color: var(--txt); }

.btn-row { display: flex; gap: 12px; flex-wrap: wrap; margin-bottom: 40px; }

/* ─ Alert ─ */
.alert-info {
  background: rgba(245,197,24,.08);
  border: 1px solid rgba(245,197,24,.3);
  border-radius: 10px;
  padding: 12px 16px;
  font-size: 0.82rem;
  color: var(--txt2);
  margin-bottom: 20px;
}

/* ─ Divider ─ */
.divider { height: 1px; background: var(--brd); margin: 32px 0; }

/* ─ Stats bar ─ */
.stats-bar {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
  margin-bottom: 24px;
}

.stat-chip {
  background: var(--s2);
  border: 1px solid var(--brd);
  border-radius: 10px;
  padding: 10px 18px;
  text-align: center;
}
.stat-chip strong {
  display: block;
  font-size: 1.2rem;
  font-weight: 700;
  color: var(--gld);
  line-height: 1;
}
.stat-chip span {
  font-size: 0.68rem;
  color: var(--txt3);
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

/* ─ Match strip (results page) ─ */
.match-strip {
  background: var(--s2);
  border: 1px solid var(--brd);
  border-radius: 14px;
  padding: 16px 22px;
  margin-bottom: 22px;
  display: flex;
  align-items: center;
  gap: 16px;
  flex-wrap: wrap;
}

.strip-vs {
  font-family: 'Bebas Neue', Impact, sans-serif;
  font-size: 1.7rem;
  letter-spacing: 2px;
  line-height: 1;
}
.strip-vs em { color: var(--gld); font-style: normal; margin: 0 8px; }
.strip-venue { font-size: 0.7rem; color: var(--txt3); margin-top: 3px; }

.strip-right { margin-left: auto; display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }

.pill {
  padding: 4px 14px;
  border-radius: 100px;
  font-size: 0.72rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 1px;
}
.pill-safe { background: rgba(34,197,94,.12); color: var(--grn); border: 1px solid rgba(34,197,94,.3); }
.pill-balanced { background: rgba(56,189,248,.12); color: var(--blu); border: 1px solid rgba(56,189,248,.3); }
.pill-risky { background: rgba(239,68,68,.12); color: var(--red); border: 1px solid rgba(239,68,68,.3); }
.pill-neutral { background: var(--s3); color: var(--txt3); border: 1px solid var(--brd); }

/* ─ Team grid ─ */
.team-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
  gap: 18px;
  margin-bottom: 40px;
}

.team-card {
  background: var(--s2);
  border: 1px solid var(--brd);
  border-radius: 16px;
  overflow: hidden;
  position: relative;
  transition: border-color .2s;
}
.team-card:hover { border-color: var(--brd2); }

.team-header {
  background: linear-gradient(135deg, #12182a, #0d1220);
  padding: 13px 16px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  border-bottom: 1px solid var(--brd);
}

.team-num {
  font-family: 'Bebas Neue', Impact, sans-serif;
  font-size: 1.05rem;
  color: var(--gld);
  letter-spacing: 2px;
}

.badge {
  font-size: 0.6rem;
  font-weight: 700;
  padding: 3px 10px;
  border-radius: 100px;
  letter-spacing: 1px;
}
.badge-free { background: var(--grn); color: #000; }
.badge-lock { background: var(--s4); color: var(--txt3); border: 1px solid var(--brd2); }

/* Captain / VC pills */
.cv-row {
  display: flex;
  gap: 8px;
  padding: 12px 14px 0;
}

.cv-pill {
  flex: 1;
  background: var(--s3);
  border: 1px solid var(--brd);
  border-radius: 10px;
  padding: 7px 10px;
  text-align: center;
}
.cv-label {
  display: block;
  font-size: 0.58rem;
  color: var(--txt3);
  letter-spacing: 0.5px;
  text-transform: uppercase;
  margin-bottom: 3px;
  font-weight: 600;
}
.cv-name { font-size: 0.8rem; font-weight: 600; display: block; }
.cv-c .cv-name { color: var(--gld); }
.cv-vc .cv-name { color: var(--blu); }

/* Player list */
.player-list {
  list-style: none;
  padding: 10px 14px 0;
}

.player-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 0;
  border-bottom: 1px solid rgba(42,43,69,.6);
  font-size: 0.78rem;
}
.player-item:last-child { border-bottom: none; }

.role-dot {
  width: 5px;
  height: 5px;
  border-radius: 50%;
  flex-shrink: 0;
}
.dot-bat { background: var(--blu); }
.dot-bowl { background: var(--ora); }
.dot-ar { background: var(--grn); }
.dot-wk { background: var(--gld); }

.player-name { flex: 1; color: var(--txt); }

.c-tag { color: var(--gld); font-size: 0.65rem; font-weight: 700; margin-left: 4px; }
.vc-tag { color: var(--blu); font-size: 0.65rem; font-weight: 700; margin-left: 4px; }

.risk-tag {
  font-size: 0.6rem;
  font-weight: 600;
  padding: 2px 7px;
  border-radius: 100px;
  flex-shrink: 0;
}
.risk-Low { background: rgba(34,197,94,.12); color: var(--grn); }
.risk-Medium { background: rgba(56,189,248,.12); color: var(--blu); }
.risk-High { background: rgba(239,68,68,.12); color: var(--red); }

/* Card footer */
.card-footer {
  padding: 10px 14px;
  border-top: 1px solid var(--brd);
  margin-top: 10px;
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.footer-split { font-size: 0.65rem; color: var(--txt3); }

.copy-btn {
  background: none;
  border: 1px solid var(--brd);
  color: var(--txt3);
  font-size: 0.7rem;
  padding: 5px 12px;
  border-radius: 7px;
  cursor: pointer;
  transition: all .18s;
  font-family: 'Inter', sans-serif;
  font-weight: 500;
}
.copy-btn:hover:not(:disabled) { border-color: var(--gld); color: var(--gld); }
.copy-btn:disabled { opacity: 0.25; cursor: default; }

/* ─ Lock Overlay ─ */
.lock-overlay {
  position: absolute;
  inset: 0;
  background: rgba(9,9,15,.88);
  backdrop-filter: blur(6px);
  -webkit-backdrop-filter: blur(6px);
  border-radius: 16px;
  z-index: 20;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
}
.lock-icon { font-size: 2.2rem; }
.lock-text {
  font-family: 'Bebas Neue', Impact, sans-serif;
  font-size: 1rem;
  letter-spacing: 3px;
  color: var(--txt3);
}
.lock-sub { font-size: 0.65rem; color: var(--txt3); }

/* ─ Unlock banner ─ */
.unlock-banner {
  background: linear-gradient(135deg, #130e00, #1f1500);
  border: 2px solid rgba(245,197,24,.35);
  border-radius: 18px;
  padding: 28px 36px;
  text-align: center;
  margin: 32px 0;
  position: relative;
  overflow: hidden;
}
.unlock-banner::before {
  content: '';
  position: absolute;
  inset: 0;
  background: radial-gradient(ellipse at center top, rgba(245,197,24,.06), transparent 70%);
}
.unlock-banner h3 {
  font-family: 'Bebas Neue', Impact, sans-serif;
  font-size: 1.9rem;
  letter-spacing: 3px;
  color: var(--gld);
  margin-bottom: 6px;
  position: relative;
}
.unlock-banner p {
  color: var(--txt3);
  font-size: 0.84rem;
  margin-bottom: 18px;
  position: relative;
}

/* ─ Ad Modal ─ */
.modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0,0,0,.92);
  z-index: 9000;
  display: flex;
  align-items: center;
  justify-content: center;
  opacity: 0;
  pointer-events: none;
  transition: opacity .25s;
}
.modal-overlay.open { opacity: 1; pointer-events: all; }

.modal-box {
  background: var(--s2);
  border: 2px solid rgba(245,197,24,.35);
  border-radius: 20px;
  padding: 36px 40px;
  max-width: 400px;
  width: 92%;
  text-align: center;
}
.modal-box h2 {
  font-family: 'Bebas Neue', Impact, sans-serif;
  font-size: 2rem;
  letter-spacing: 3px;
  color: var(--gld);
  margin-bottom: 8px;
}
.modal-box p { color: var(--txt3); font-size: 0.83rem; margin-bottom: 0; }

.ad-sim-box {
  background: var(--s1);
  border: 2px dashed var(--brd2);
  border-radius: 14px;
  padding: 28px 20px;
  margin: 18px 0;
}
.ad-sim-icon { font-size: 3rem; margin-bottom: 8px; }
.ad-sim-text { font-size: 0.85rem; color: var(--txt2); }
.ad-sim-sub { font-size: 0.7rem; color: var(--txt3); margin-top: 4px; }

.ad-progress {
  height: 6px;
  background: var(--brd);
  border-radius: 100px;
  overflow: hidden;
  margin-top: 16px;
}
.ad-progress-bar {
  height: 100%;
  background: linear-gradient(90deg, var(--ora), var(--gld));
  border-radius: 100px;
  width: 0%;
  transition: width .1s linear;
}
.ad-timer {
  font-size: 1.1rem;
  font-weight: 700;
  color: var(--ora);
  margin-top: 10px;
}

/* ─ Toast ─ */
.toast {
  position: fixed;
  bottom: 24px;
  right: 24px;
  z-index: 9999;
  padding: 10px 20px;
  border-radius: 10px;
  font-size: 0.82rem;
  font-weight: 600;
  transform: translateY(60px);
  opacity: 0;
  transition: all .3s ease;
  pointer-events: none;
}
.toast.show { transform: translateY(0); opacity: 1; }

/* ─ Results page top bar ─ */
.results-topbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
  gap: 12px;
  margin-bottom: 22px;
}

/* ─ Animations ─ */
@keyframes fadeUp {
  from { opacity: 0; transform: translateY(18px); }
  to { opacity: 1; transform: translateY(0); }
}
.fade-up { animation: fadeUp .4s ease both; }

/* ─ Print ─ */
@media print {
  header, nav, .unlock-banner, .btn, .copy-btn, .lock-overlay,
  .modal-overlay, .toast, .tab-bar { display: none !important; }
  body { background: #fff; color: #000; }
  .team-card { border: 1px solid #ddd; break-inside: avoid; background: #fff; }
  .team-header { background: #f5f5f5; }
  .team-num { color: #c8a200 !important; -webkit-text-fill-color: #c8a200; }
  .cv-name { color: #c8a200 !important; }
  .player-name { color: #000; }
}
</style>
"""

# ─── Home Page ─────────────────────────────────────────────────────────────────

HOME_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>FantasyXI — Super 8s Team Generator</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
""" + _CSS + """
</head>
<body>

<header>
  <div>
    <div class="logo">⚡ FantasyXI</div>
    <div class="logo-sub">ICC T20 World Cup 2026 · Super 8s</div>
  </div>
</header>

<div class="hero z1">
  <h1>GENERATE<br>YOUR DREAM XI</h1>
  <p>Smart distribution engine · 20 unique fantasy teams · Super 8s Edition</p>
  <div class="tournament-pill">🏆 {{ tournament }}</div>
</div>

<div class="wrap z1">

  <!-- Tabs -->
  <div class="tab-bar">
    <button class="tab-btn active" id="tabBtnUp" onclick="showTab('up', this)">📅 Upcoming Matches</button>
    <button class="tab-btn" id="tabBtnMan" onclick="showTab('man', this)">⚙ Manual Selection</button>
  </div>

  <!-- ── UPCOMING MATCHES ── -->
  <div id="tab-up">
    <div class="sh">Select a Match</div>
    <div class="match-grid">
    {% for m in matches %}
      <div class="match-card" id="mc-{{ m.match_id }}"
           onclick="selectMatch('{{ m.match_id }}','{{ m.team1 }}','{{ m.team2 }}','{{ m.date }}','{{ m.venue | replace("'","") }}', this)">
        <div class="match-time-badge">{{ m.time }}</div>
        <div class="match-id">📅 {{ m.date }} &nbsp;·&nbsp; {{ m.match_id }}</div>
        <div class="match-teams">{{ m.team1 }}<em>VS</em>{{ m.team2 }}</div>
        <div class="match-venue">📍 {{ m.venue }}</div>
      </div>
    {% endfor %}
    </div>
    <div class="alert-info" id="sel-info" style="display:none;"></div>
  </div>

  <!-- ── MANUAL SELECTION ── -->
  <div id="tab-man" style="display:none;">
    <div class="sh">Manual Team Selection</div>
    <div class="input-row">
      <div class="input-group">
        <label>Team 1</label>
        <select id="mt1">
          {% for t in all_teams %}<option value="{{ t.team }}">{{ t.team }}</option>{% endfor %}
        </select>
      </div>
      <div class="input-group">
        <label>Team 2</label>
        <select id="mt2">
          {% for t in all_teams %}
          <option value="{{ t.team }}"{% if loop.index == 2 %} selected{% endif %}>{{ t.team }}</option>
          {% endfor %}
        </select>
      </div>
    </div>
    <button class="btn btn-ghost" onclick="setManual()" style="margin-bottom: 24px;">
      Confirm Teams →
    </button>
  </div>

  <div class="divider"></div>

  <!-- ── MODE SELECTION ── -->
  <div class="sh">Generation Mode</div>
  <div class="mode-grid">
    <div class="mode-card safe" onclick="selectMode('safe', this)">
      <div class="mode-icon">🛡</div>
      <div class="mode-name">Safe</div>
      <div class="mode-desc">Playing XI only · Low-risk captains · Conservative, consistent picks</div>
    </div>
    <div class="mode-card balanced" onclick="selectMode('balanced', this)">
      <div class="mode-icon">⚖️</div>
      <div class="mode-name">Balanced</div>
      <div class="mode-desc">9 from XI + 2 bench · Mixed risk captains · Smart rotation</div>
    </div>
    <div class="mode-card risky" onclick="selectMode('risky', this)">
      <div class="mode-icon">🔥</div>
      <div class="mode-name">Risky</div>
      <div class="mode-desc">Full bench included · High-risk stars · Maximum points ceiling</div>
    </div>
  </div>

  <!-- ── ADVANCED CRITERIA ── -->
  <div class="sh">Advanced Criteria</div>
  <div class="input-row">
    <div class="input-group">
      <label>Min appearances / player</label>
      <input type="number" id="mn" value="3" min="1" max="20">
    </div>
    <div class="input-group">
      <label>Max appearances / player</label>
      <input type="number" id="mx" value="15" min="1" max="20">
    </div>
    <div class="input-group">
      <label>Teams to generate (max 20)</label>
      <input type="number" id="nt" value="20" min="5" max="20">
    </div>
  </div>

  <div class="crit-grid">
    <div class="crit-item"><input type="checkbox" id="c1" checked><label for="c1">✔ Balanced 6:5 team-split rotation</label></div>
    <div class="crit-item"><input type="checkbox" id="c2" checked><label for="c2">✔ Differential (High risk) players ≥ 3 appearances</label></div>
    <div class="crit-item"><input type="checkbox" id="c3" checked><label for="c3">✔ Star (Low risk) players ≥ 10 appearances</label></div>
    <div class="crit-item"><input type="checkbox" id="c4" checked><label for="c4">✔ Every player becomes captain at least once</label></div>
    <div class="crit-item"><input type="checkbox" id="c5" checked><label for="c5">✔ Top 5 players rotated more frequently</label></div>
    <div class="crit-item"><input type="checkbox" id="c6" checked><label for="c6">✔ At least 5 different C/VC combinations</label></div>
    <div class="crit-item"><input type="checkbox" id="c7" checked><label for="c7">✔ Avoid repeating same C/VC pair</label></div>
    <div class="crit-item"><input type="checkbox" id="c8" checked><label for="c8">✔ Risk-based captain weighting</label></div>
    <div class="crit-item"><input type="checkbox" id="c9" checked><label for="c9">✔ Bench players appear in ≥ 3 teams</label></div>
    <div class="crit-item"><input type="checkbox" id="c10" checked><label for="c10">✔ At least 3 all-rounders in risky mode</label></div>
    <div class="crit-item"><input type="checkbox" id="c11" checked><label for="c11">✔ Captain must not repeat > 3 consecutive teams</label></div>
    <div class="crit-item"><input type="checkbox" id="c12" checked><label for="c12">✔ No identical team combination allowed</label></div>
    <div class="crit-item"><input type="checkbox" id="c13" checked><label for="c13">✔ Max 7 players from one team per fantasy XI</label></div>
    <div class="crit-item"><input type="checkbox" id="c14" checked><label for="c14">✔ Role constraints: 1–4 WK / 3–6 BAT / 1–4 AR / 3–6 BOWL</label></div>
    <div class="crit-item"><input type="checkbox" id="c15" checked><label for="c15">✔ At least 1 all-rounder captain in first 5 teams</label></div>
  </div>

  <div class="btn-row">
    <button class="btn btn-gold" onclick="doGenerate()">⚡ Generate 20 Teams</button>
    <button class="btn btn-ghost" onclick="resetAll()">↺ Reset</button>
  </div>

</div><!-- /wrap -->

<!-- Ad Modal -->
<div class="modal-overlay" id="adModal">
  <div class="modal-box">
    <h2>📺 Watch Ad</h2>
    <p>Watch a 5-second ad to unlock all remaining teams</p>
    <div class="ad-sim-box">
      <div class="ad-sim-icon">📺</div>
      <div class="ad-sim-text">Simulated Advertisement</div>
      <div class="ad-sim-sub">No real ad SDK required</div>
      <div class="ad-progress"><div class="ad-progress-bar" id="adBar"></div></div>
      <div class="ad-timer" id="adTimer">⏳ 5s</div>
    </div>
    <button class="btn btn-ghost" onclick="closeAd()" style="width:100%;">✕ Close</button>
  </div>
</div>

<div class="toast" id="toast"></div>

<script>
var selTeam1 = null, selTeam2 = null, selMatchId = null, selMode = null, adInterval = null;

function showTab(id, el) {
  document.getElementById('tab-up').style.display = id === 'up' ? '' : 'none';
  document.getElementById('tab-man').style.display = id === 'man' ? '' : 'none';
  document.querySelectorAll('.tab-btn').forEach(function(b){ b.classList.remove('active'); });
  el.classList.add('active');
}

function selectMatch(id, t1, t2, date, venue, el) {
  selMatchId = id; selTeam1 = t1; selTeam2 = t2;
  document.querySelectorAll('.match-card').forEach(function(c){ c.classList.remove('selected'); });
  el.classList.add('selected');
  var info = document.getElementById('sel-info');
  info.style.display = '';
  info.innerHTML = '✅ Selected: <strong>' + t1 + ' vs ' + t2 + '</strong> &nbsp;·&nbsp; ' + date + ' &nbsp;·&nbsp; 📍 ' + venue + ' — Now choose a generation mode below.';
}

function setManual() {
  var t1 = document.getElementById('mt1').value;
  var t2 = document.getElementById('mt2').value;
  if (t1 === t2) { showToast('Please select two different teams!', '#ef4444'); return; }
  selTeam1 = t1; selTeam2 = t2; selMatchId = 'manual';
  showToast('Teams confirmed! Now choose a mode below.');
}

function selectMode(m, el) {
  selMode = m;
  document.querySelectorAll('.mode-card').forEach(function(c){ c.classList.remove('active'); });
  el.classList.add('active');
}

function doGenerate() {
  if (!selTeam1 || !selTeam2) { showToast('Please select a match first!', '#ef4444'); return; }
  if (!selMode) { showToast('Please choose Safe / Balanced / Risky mode!', '#ef4444'); return; }
  var cr = {};
  for (var i = 1; i <= 15; i++) cr['c' + i] = document.getElementById('c' + i).checked;
  var payload = {
    team1: selTeam1, team2: selTeam2, match_id: selMatchId, mode: selMode,
    mn: parseInt(document.getElementById('mn').value),
    mx: parseInt(document.getElementById('mx').value),
    nt: Math.min(parseInt(document.getElementById('nt').value), 20),
    cr: cr
  };
  var form = document.createElement('form');
  form.method = 'POST'; form.action = '/generate';
  var inp = document.createElement('input');
  inp.type = 'hidden'; inp.name = 'payload'; inp.value = JSON.stringify(payload);
  form.appendChild(inp); document.body.appendChild(form); form.submit();
}

function resetAll() {
  selTeam1 = selTeam2 = selMatchId = selMode = null;
  document.querySelectorAll('.match-card').forEach(function(c){ c.classList.remove('selected'); });
  document.querySelectorAll('.mode-card').forEach(function(c){ c.classList.remove('active'); });
  document.getElementById('sel-info').style.display = 'none';
}

function openAd() {
  document.getElementById('adModal').classList.add('open');
  var cd = 5;
  document.getElementById('adBar').style.width = '0%';
  document.getElementById('adTimer').textContent = '⏳ ' + cd + 's';
  adInterval = setInterval(function() {
    cd--;
    document.getElementById('adBar').style.width = ((5 - cd) / 5 * 100) + '%';
    document.getElementById('adTimer').textContent = cd > 0 ? '⏳ ' + cd + 's' : '✅ Done!';
    if (cd <= 0) {
      clearInterval(adInterval);
      setTimeout(function() {
        document.getElementById('adModal').classList.remove('open');
        unlockAll();
      }, 600);
    }
  }, 1000);
}

function closeAd() { clearInterval(adInterval); document.getElementById('adModal').classList.remove('open'); }

function unlockAll() {
  fetch('/unlock', { method: 'POST' }).then(function(r){ return r.json(); }).then(function(d){
    if (d.success) {
      document.querySelectorAll('.lock-overlay').forEach(function(e){
        e.style.transition = 'opacity .4s';
        e.style.opacity = '0';
        setTimeout(function(){ e.remove(); }, 400);
      });
      document.querySelectorAll('.copy-btn').forEach(function(b){ b.disabled = false; });
      showToast('🎉 All teams unlocked!');
    }
  });
}

function showToast(msg, bg) {
  bg = bg || '#22c55e';
  var t = document.getElementById('toast');
  t.textContent = msg; t.style.background = bg; t.style.color = bg === '#22c55e' ? '#000' : '#fff';
  t.classList.add('show');
  setTimeout(function(){ t.classList.remove('show'); }, 3000);
}

function copyTeam(idx) {
  var cards = document.querySelectorAll('.team-card');
  var card = cards[idx];
  var num = card.querySelector('.team-num').textContent;
  var cvNms = card.querySelectorAll('.cv-name');
  var cap = cvNms[0] ? cvNms[0].textContent.trim() : '';
  var vc = cvNms[1] ? cvNms[1].textContent.trim() : '';
  var txt = num + '\\nCaptain (2×): ' + cap + '\\nVice Captain (1.5×): ' + vc + '\\n\\n';
  card.querySelectorAll('.player-name').forEach(function(s){ txt += s.textContent.trim() + '\\n'; });
  navigator.clipboard.writeText(txt).then(function(){ showToast('Team ' + (idx + 1) + ' copied!'); });
}
</script>
</body>
</html>
"""

# ─── Results Page ──────────────────────────────────────────────────────────────

RESULTS_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>FantasyXI — Generated Teams</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
""" + _CSS + """
</head>
<body>

<header>
  <div>
    <div class="logo">⚡ FantasyXI</div>
    <div class="logo-sub">ICC T20 World Cup 2026 · Super 8s</div>
  </div>
  <nav>
    <a href="/">← Home</a>
    <a href="#" onclick="window.print(); return false;">🖨 Print</a>
    <a href="/export_pdf" id="pdfBtn" {% if not unlocked %}style="display:none"{% endif %}>📄 PDF</a>
  </nav>
</header>

<div class="wrap z1">

  <!-- Match strip -->
  <div class="match-strip">
    <div>
      <div class="strip-vs">{{ team1 }}<em>VS</em>{{ team2 }}</div>
      {% if venue %}<div class="strip-venue">📍 {{ venue }}</div>{% endif %}
    </div>
    <div class="strip-right">
      <span class="pill pill-{{ mode }}">{{ mode | upper }} MODE</span>
      <span class="pill pill-neutral">{{ teams | length }} Teams</span>
    </div>
  </div>

  <!-- Stats bar -->
  <div class="stats-bar">
    <div class="stat-chip"><strong>{{ teams | length }}</strong><span>Generated</span></div>
    <div class="stat-chip"><strong>3</strong><span>Free</span></div>
    <div class="stat-chip"><strong>{{ teams | length - 3 }}</strong><span>Locked</span></div>
    <div class="stat-chip"><strong>{{ unique_caps }}</strong><span>Unique Captains</span></div>
    <div class="stat-chip"><strong>{{ cv_combos }}</strong><span>C/VC Combos</span></div>
  </div>

  <!-- Top bar -->
  <div class="results-topbar">
    <div class="sh" style="margin-bottom:0;">Generated Teams</div>
    {% if unlocked %}
    <a href="/export_pdf" class="btn btn-green" style="font-size:.9rem;padding:9px 20px;">📄 Export PDF</a>
    {% endif %}
  </div>

  <!-- Team cards -->
  <div class="team-grid">
  {% for t in teams %}
    <div class="team-card fade-up" style="animation-delay: {{ loop.index0 * 0.035 }}s;">

      <div class="team-header">
        <div class="team-num">Team {{ loop.index }}</div>
        {% if loop.index <= 3 %}
          <span class="badge badge-free">FREE ✓</span>
        {% else %}
          <span class="badge badge-lock">🔒 LOCKED</span>
        {% endif %}
      </div>

      <!-- C / VC -->
      <div class="cv-row">
        <div class="cv-pill cv-c">
          <span class="cv-label">Captain (2×)</span>
          <span class="cv-name">{{ t.captain }}</span>
        </div>
        <div class="cv-pill cv-vc">
          <span class="cv-label">Vice Captain (1.5×)</span>
          <span class="cv-name">{{ t.vice_captain }}</span>
        </div>
      </div>

      <!-- Players -->
      <ul class="player-list">
      {% for p in t.players %}
        <li class="player-item">
          {% if p.role == 'Batsman' %}<div class="role-dot dot-bat" title="Batsman"></div>
          {% elif p.role == 'Bowler' %}<div class="role-dot dot-bowl" title="Bowler"></div>
          {% elif p.role == 'All-rounder' %}<div class="role-dot dot-ar" title="All-rounder"></div>
          {% else %}<div class="role-dot dot-wk" title="Wicketkeeper-Batsman"></div>{% endif %}
          <span class="player-name">
            {{ p.name }}
            {% if p.name == t.captain %}<span class="c-tag">(C)</span>{% endif %}
            {% if p.name == t.vice_captain %}<span class="vc-tag">(VC)</span>{% endif %}
          </span>
          <span class="risk-tag risk-{{ p.risk_level }}">{{ p.risk_level }}</span>
        </li>
      {% endfor %}
      </ul>

      <!-- Footer -->
      <div class="card-footer">
        <div class="footer-split">
          {{ t.from_t1 }} from {{ team1 }} &nbsp;·&nbsp; {{ t.from_t2 }} from {{ team2 }}
        </div>
        {% if loop.index <= 3 %}
          <button class="copy-btn" onclick="copyTeam({{ loop.index0 }})">📋 Copy</button>
        {% else %}
          <button class="copy-btn" onclick="copyTeam({{ loop.index0 }})" {% if not unlocked %}disabled{% endif %}>📋 Copy</button>
        {% endif %}
      </div>

      <!-- Lock overlay -->
      {% if loop.index > 3 and not unlocked %}
      <div class="lock-overlay">
        <div class="lock-icon">🔒</div>
        <div class="lock-text">LOCKED</div>
        <div class="lock-sub">Watch ad to unlock</div>
      </div>
      {% endif %}

    </div>
  {% endfor %}
  </div>

  <!-- Unlock / Export -->
  {% if not unlocked %}
  <div class="unlock-banner" id="unlockBanner">
    <h3>🎬 Unlock All {{ teams | length - 3 }} Remaining Teams</h3>
    <p>Watch one short 5-second simulated ad — no real ad SDK required.</p>
    <button class="btn btn-orange" onclick="openAd()">▶ Watch 1 Ad to Unlock All Teams</button>
  </div>
  {% else %}
  <div style="text-align:center; margin: 36px 0;">
    <a href="/export_pdf" class="btn btn-green">📄 Export All {{ teams | length }} Teams as PDF</a>
  </div>
  {% endif %}

</div><!-- /wrap -->

<!-- Ad Modal -->
<div class="modal-overlay" id="adModal">
  <div class="modal-box">
    <h2>📺 Watch Ad</h2>
    <p>5-second ad · simulated · no real SDK</p>
    <div class="ad-sim-box">
      <div class="ad-sim-icon">📺</div>
      <div class="ad-sim-text">Advertisement</div>
      <div class="ad-sim-sub">Simulated for demo purposes</div>
      <div class="ad-progress"><div class="ad-progress-bar" id="adBar"></div></div>
      <div class="ad-timer" id="adTimer">⏳ 5s</div>
    </div>
    <button class="btn btn-ghost" onclick="closeAd()" style="width:100%;">✕ Close</button>
  </div>
</div>

<div class="toast" id="toast"></div>

<script>
var adInterval = null;

function openAd() {
  document.getElementById('adModal').classList.add('open');
  var cd = 5;
  document.getElementById('adBar').style.width = '0%';
  document.getElementById('adTimer').textContent = '⏳ ' + cd + 's';
  adInterval = setInterval(function() {
    cd--;
    document.getElementById('adBar').style.width = ((5 - cd) / 5 * 100) + '%';
    document.getElementById('adTimer').textContent = cd > 0 ? '⏳ ' + cd + 's' : '✅ Done!';
    if (cd <= 0) {
      clearInterval(adInterval);
      setTimeout(function() {
        document.getElementById('adModal').classList.remove('open');
        unlockAll();
      }, 600);
    }
  }, 1000);
}

function closeAd() {
  clearInterval(adInterval);
  document.getElementById('adModal').classList.remove('open');
}

function unlockAll() {
  fetch('/unlock', { method: 'POST' })
    .then(function(r) { return r.json(); })
    .then(function(d) {
      if (!d.success) return;
      document.querySelectorAll('.lock-overlay').forEach(function(el) {
        el.style.transition = 'opacity .4s';
        el.style.opacity = '0';
        setTimeout(function() { el.remove(); }, 400);
      });
      document.querySelectorAll('.copy-btn').forEach(function(b) { b.disabled = false; });
      var banner = document.getElementById('unlockBanner');
      if (banner) {
        banner.innerHTML = '<h3 style="color:var(--grn)">✅ All Teams Unlocked!</h3><div style="margin-top:16px;"><a href="/export_pdf" class="btn btn-green">📄 Export All Teams as PDF</a></div>';
      }
      var pdfBtn = document.getElementById('pdfBtn');
      if (pdfBtn) pdfBtn.style.display = '';
      showToast('🎉 All {{ teams | length - 3 }} teams unlocked!');
    });
}

function showToast(msg, bg) {
  bg = bg || '#22c55e';
  var t = document.getElementById('toast');
  t.textContent = msg; t.style.background = bg; t.style.color = '#000';
  t.classList.add('show');
  setTimeout(function() { t.classList.remove('show'); }, 3200);
}

function copyTeam(idx) {
  var cards = document.querySelectorAll('.team-card');
  var card = cards[idx];
  var num = card.querySelector('.team-num').textContent;
  var cvNms = card.querySelectorAll('.cv-name');
  var cap = cvNms[0] ? cvNms[0].textContent.trim() : '';
  var vc  = cvNms[1] ? cvNms[1].textContent.trim() : '';
  var txt = num + '\\nCaptain (2x): ' + cap + '\\nVice Captain (1.5x): ' + vc + '\\n\\n';
  card.querySelectorAll('.player-name').forEach(function(s) {
    txt += s.textContent.replace(/\\s+/g, ' ').trim() + '\\n';
  });
  navigator.clipboard.writeText(txt).then(function() { showToast('Team ' + (idx + 1) + ' copied!'); });
}
</script>
</body>
</html>
"""

# ─── Routes ───────────────────────────────────────────────────────────────────

@app.route("/")
def home():
    td = load_teams()
    md = load_matches()
    return render_template_string(
        HOME_PAGE,
        tournament=td.get("tournament", "ICC T20 WC 2026"),
        matches=md["matches"],
        all_teams=td["teams"],
    )


@app.route("/generate", methods=["POST"])
def generate():
    try:
        p = json.loads(request.form.get("payload", "{}"))
    except Exception:
        return "Bad payload", 400

    team1    = p.get("team1", "")
    team2    = p.get("team2", "")
    match_id = p.get("match_id", "")
    mode     = p.get("mode", "balanced")
    mn       = int(p.get("mn", 3))
    mx       = int(p.get("mx", 15))
    nt       = min(int(p.get("nt", 20)), 20)
    cr       = p.get("cr", {})

    tbn = teams_by_name()
    if team1 not in tbn: return f"Team not found: {team1!r}", 400
    if team2 not in tbn: return f"Team not found: {team2!r}", 400

    teams, ucaps, cvcombos = gen_teams(team1, team2, mode, cr, mn, mx, nt)

    venue = ""
    if match_id != "manual":
        for m in load_matches()["matches"]:
            if m["match_id"] == match_id:
                venue = m.get("venue", "")
                break

    session["gen"] = {"teams": teams, "team1": team1, "team2": team2,
                      "mode": mode, "venue": venue}
    session["unlocked"] = False

    return render_template_string(
        RESULTS_PAGE,
        teams=teams, team1=team1, team2=team2,
        mode=mode, venue=venue, match_id=match_id,
        unique_caps=ucaps, cv_combos=cvcombos,
        unlocked=False,
    )


@app.route("/unlock", methods=["POST"])
def unlock():
    session["unlocked"] = True
    return jsonify({"success": True})


@app.route("/export_pdf")
def export_pdf():
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.units import cm
        from reportlab.lib import colors
        from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer,
                                        Table, TableStyle, HRFlowable, PageBreak)
        from reportlab.lib.styles import ParagraphStyle
    except ImportError:
        return "pip install reportlab --break-system-packages", 500

    gen      = session.get("gen", {})
    teams    = gen.get("teams", [])
    if not teams:
        return "No teams in session — generate first.", 400

    team1    = gen.get("team1", "Team 1")
    team2    = gen.get("team2", "Team 2")
    mode     = gen.get("mode", "balanced").upper()
    venue    = gen.get("venue", "")
    unlocked = session.get("unlocked", False)

    GOLD  = colors.HexColor("#f5c518")
    DARK  = colors.HexColor("#141926")
    DARK2 = colors.HexColor("#0d1220")
    MUTED = colors.HexColor("#64748b")
    GRN   = colors.HexColor("#22c55e")
    BLU   = colors.HexColor("#38bdf8")
    ORA   = colors.HexColor("#ff5f1f")
    WHT   = colors.white

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4,
                            leftMargin=1.4*cm, rightMargin=1.4*cm,
                            topMargin=1.8*cm, bottomMargin=1.8*cm)

    def sty(n, **kw): return ParagraphStyle(n, **kw)

    s_title = sty("t",  fontSize=22, textColor=GOLD, fontName="Helvetica-Bold", alignment=1, spaceAfter=4)
    s_sub   = sty("s",  fontSize=9,  textColor=MUTED, alignment=1, spaceAfter=5)
    s_th    = sty("th", fontSize=13, textColor=GOLD, fontName="Helvetica-Bold", spaceAfter=5)
    s_cv    = sty("cv", fontSize=9,  textColor=WHT, spaceAfter=4)
    s_ft    = sty("ft", fontSize=7.5, textColor=MUTED, spaceBefore=3)

    story = []
    story.append(Paragraph("FantasyXI", s_title))
    story.append(Paragraph("ICC Men's T20 World Cup 2026 - Super 8s", s_sub))
    story.append(Paragraph(f"{team1}  VS  {team2}  |  {mode} Mode", s_sub))
    if venue:
        story.append(Paragraph(f"Venue: {venue}", s_sub))
    story.append(Spacer(1, .2*cm))
    story.append(HRFlowable(width="100%", thickness=1, color=GOLD))
    story.append(Spacer(1, .4*cm))

    max_idx = len(teams) if unlocked else 3

    for idx, team in enumerate(teams[:max_idx]):
        story.append(Paragraph(f"Team {idx + 1}", s_th))
        story.append(Paragraph(
            f"<b><font color='#f5c518'>Captain (2x):</font></b> {team['captain']}     "
            f"<b><font color='#38bdf8'>Vice Captain (1.5x):</font></b> {team['vice_captain']}", s_cv))

        rows = [["#", "Player", "Role", "Risk"]]
        for pi, p in enumerate(team["players"]):
            tag = " (C)" if p["name"] == team["captain"] else (" (VC)" if p["name"] == team["vice_captain"] else "")
            rows.append([str(pi + 1), p["name"] + tag, p["role"], p["risk_level"]])

        tbl = Table(rows, colWidths=[.7*cm, 7*cm, 4.5*cm, 2.5*cm])
        tbl.setStyle(TableStyle([
            ("BACKGROUND",    (0,0), (-1,0),   DARK2),
            ("TEXTCOLOR",     (0,0), (-1,0),   GOLD),
            ("FONTNAME",      (0,0), (-1,0),   "Helvetica-Bold"),
            ("FONTSIZE",      (0,0), (-1,-1),  8.5),
            ("TEXTCOLOR",     (0,1), (-1,-1),  WHT),
            ("ROWBACKGROUNDS",(0,1), (-1,-1),  [DARK, colors.HexColor("#18202e")]),
            ("GRID",          (0,0), (-1,-1),  .3, colors.HexColor("#2a2b45")),
            ("ALIGN",         (0,0), (0,-1),   "CENTER"),
            ("TOPPADDING",    (0,0), (-1,-1),  5),
            ("BOTTOMPADDING", (0,0), (-1,-1),  5),
            ("LEFTPADDING",   (0,0), (-1,-1),  6),
        ]))
        story.append(tbl)
        story.append(Paragraph(
            f"{team['from_t1']} players from {team1} | {team['from_t2']} players from {team2}", s_ft))
        story.append(Spacer(1, .5*cm))
        if (idx + 1) % 2 == 0 and idx < max_idx - 1:
            story.append(PageBreak())

    doc.build(story)
    buf.seek(0)
    return send_file(buf, mimetype="application/pdf", as_attachment=True,
                     download_name=f"FantasyXI_{team1}_vs_{team2}.pdf")


# ─── Run ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    app.run(debug=True, port=5000)