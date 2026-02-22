# =============================================================================
# FantasyXI — ICC T20 World Cup 2026 Super 8s · Fantasy Team Generator
# Single-file Flask app | Two JSON files only | AdSense-ready | v2.0
# =============================================================================

import json, random, hashlib, io, datetime
from flask import (Flask, render_template_string, request,
                   jsonify, send_file, session, Response)
from collections import defaultdict

app = Flask(__name__)
app.secret_key = "fantasyxi_t20wc_2026_sk_v2"

# ─── Data helpers ─────────────────────────────────────────────────────────────

def load_teams():
    with open("teams.json") as f: return json.load(f)

def load_matches():
    with open("matches.json") as f: return json.load(f)

def teams_by_name():
    return {t["team"]: t for t in load_teams()["teams"]}

def get_xi(team_name):
    t = teams_by_name().get(team_name)
    if not t: return [], team_name
    return t["players"][:11], t["team"]

# ─── Generation engine ────────────────────────────────────────────────────────

def hash_team(ids):
    return hashlib.md5(",".join(sorted(ids)).encode()).hexdigest()

def risk_weight(p, mode):
    r = p.get("risk_level", "Medium")
    if mode == "safe":
        return {"Low": 5, "Medium": 2, "High": 0.5}[r]
    elif mode == "balanced":
        return {"Low": 3, "Medium": 4, "High": 2}[r]
    else:
        return {"Low": 1.5, "Medium": 3, "High": 6}[r]

def roles_ok(players):
    roles = [p["role"] for p in players]
    wk   = roles.count("Wicketkeeper-Batsman")
    bat  = roles.count("Batsman")
    ar   = roles.count("All-rounder")
    bowl = roles.count("Bowler")
    return (1 <= wk <= 4) and (3 <= bat <= 6) and (1 <= ar <= 4) and (3 <= bowl <= 6)

def gen_teams(team1, team2, mode, cr, nt=20, adv=None):
    if adv is None: adv = {}
    xi1, _ = get_xi(team1)
    xi2, _ = get_xi(team2)

    # Apply lock/exclude filters
    locked_ids   = set(adv.get("locked", []))
    excluded_ids = set(adv.get("excluded", []))
    max_from_one = int(adv.get("max_from_one", 7))
    exposure_pct = float(adv.get("exposure_pct", 75)) / 100.0  # default 75%

    pool1 = [p for p in xi1 if p["id"] not in excluded_ids]
    pool2 = [p for p in xi2 if p["id"] not in excluded_ids]

    appear   = defaultdict(int)
    cap_cnt  = defaultdict(int)
    vc_cnt   = defaultdict(int)
    cv_pairs = set()
    th_set   = set()
    last_cap = []
    result   = []

    def cap_pool(players):
        if mode == "safe":
            e = [p for p in players if p["risk_level"] == "Low"]
        elif mode == "balanced":
            e = [p for p in players if p["risk_level"] in ("Low", "Medium")]
        else:
            e = players[:]
        return e or players[:]

    def pick_unique(pool, weights, n, locked):
        locked_players = [p for p in pool if p["id"] in locked]
        free_pool = [p for p in pool if p["id"] not in locked]
        free_weights = [w for p, w in zip(pool, weights) if p["id"] not in locked]

        need = n - len(locked_players)
        if need < 0: locked_players = locked_players[:n]
        need = max(need, 0)

        seen = [p["id"] for p in locked_players]
        out  = locked_players[:]

        if need > 0 and free_pool:
            tries = random.choices(free_pool, weights=free_weights or [1]*len(free_pool),
                                   k=min(len(free_pool), need * 5))
            for p in tries:
                if p["id"] not in seen:
                    # exposure limit
                    if appear[p["id"]] >= int(nt * exposure_pct): continue
                    seen.append(p["id"]); out.append(p)
                if len(out) == n: break
            rest = [p for p in free_pool if p["id"] not in seen]
            random.shuffle(rest)
            for p in rest:
                if len(out) == n: break
                out.append(p); seen.append(p["id"])
        return out

    for idx in range(nt):
        valid = False; attempts = 0
        captain = vice_captain = None
        sel1 = sel2 = []

        while not valid and attempts < 400:
            attempts += 1
            n1, n2 = (6, 5) if (cr.get("c1", True) and idx % 2 == 0) else (5, 6)

            # Differential inclusion: occasionally swap weights
            w1 = [risk_weight(p, mode) for p in pool1]
            w2 = [risk_weight(p, mode) for p in pool2]

            if adv.get("differential", False) and idx >= 10:
                # Boost lower-appearance players for diversity
                w1 = [w * max(0.5, 1 - appear[p["id"]] / max(nt, 1)) for p, w in zip(pool1, w1)]
                w2 = [w * max(0.5, 1 - appear[p["id"]] / max(nt, 1)) for p, w in zip(pool2, w2)]

            sel1 = pick_unique(pool1, w1, n1, locked_ids)
            sel2 = pick_unique(pool2, w2, n2, locked_ids)
            if len(sel1) != n1 or len(sel2) != n2: continue
            players = sel1 + sel2

            if cr.get("c14", True) and not roles_ok(players): continue

            # Max players from one team
            max_one = max_from_one if adv.get("max_from_one") else 7
            if cr.get("c13", True) and (len(sel1) > max_one or len(sel2) > max_one): continue

            h = hash_team([p["id"] for p in players])
            if cr.get("c12", True) and h in th_set: continue

            # Captain selection
            cp = cap_pool(players)
            def cw(p):
                b = risk_weight(p, mode)
                b /= (1 + cap_cnt[p["id"]] * 0.5)
                return max(b, 0.05)
            cws = [cw(p) for p in cp]

            if cr.get("c11", True) and len(last_cap) >= 3 and len(set(last_cap[-3:])) == 1:
                forb = last_cap[-3]
                alt = [(p, w) for p, w in zip(cp, cws) if p["id"] != forb]
                if alt:
                    cp, cws = zip(*alt); cp, cws = list(cp), list(cws)

            captain = random.choices(cp, weights=cws, k=1)[0]

            if cr.get("c15", True) and idx < 5:
                ar_done = any(
                    any(p["id"] == cid and p["role"] == "All-rounder" for p in players)
                    for cid in cap_cnt
                )
                if not ar_done and idx == 4:
                    arc = [p for p in cp if p["role"] == "All-rounder"]
                    if arc: captain = random.choice(arc)

            # Vice-captain selection
            vp = [p for p in players if p["id"] != captain["id"]]
            if not vp: continue
            def vw(p):
                b = risk_weight(p, mode)
                b /= (1 + vc_cnt[p["id"]] * 0.3)
                return max(b, 0.05)
            vws = [vw(p) for p in vp]
            if cr.get("c7", True):
                alt = [(p, w) for p, w in zip(vp, vws) if (captain["id"], p["id"]) not in cv_pairs]
                if alt:
                    vp, vws = zip(*alt); vp, vws = list(vp), list(vws)

            vice_captain = random.choices(vp, weights=vws, k=1)[0]
            cv = (captain["id"], vice_captain["id"])
            if cr.get("c6", True) and len(cv_pairs) < 5 and len(result) >= 5:
                if cv in cv_pairs and attempts < 150: continue

            # Unique C/VC per team (advanced)
            if adv.get("unique_cap", False):
                if captain["id"] in [r.get("_cap_id") for r in result]: continue
            if adv.get("unique_vc", False):
                if vice_captain["id"] in [r.get("_vc_id") for r in result]: continue

            valid = True
            th_set.add(h); cv_pairs.add(cv)
            cap_cnt[captain["id"]] += 1
            vc_cnt[vice_captain["id"]] += 1
            last_cap.append(captain["id"])
            for p in players: appear[p["id"]] += 1

        result.append({
            "players":     (sel1 + sel2) if (sel1 or sel2) else [],
            "captain":     captain["name"] if captain else "—",
            "vice_captain": vice_captain["name"] if vice_captain else "—",
            "_cap_id":     captain["id"] if captain else None,
            "_vc_id":      vice_captain["id"] if vice_captain else None,
            "from_t1":     len(sel1),
            "from_t2":     len(sel2),
        })

    return result, len(cap_cnt), len(cv_pairs)


# ═══════════════════════════════════════════════════════════════════════════════
# ─── Shared CSS ───────────────────────────────────────────────────────────────
# ═══════════════════════════════════════════════════════════════════════════════

_CSS = """
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="theme-color" content="#08090f">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Barlow+Condensed:wght@400;600;700;800&family=DM+Sans:wght@300;400;500;600&display=swap" rel="stylesheet">
<style>
:root{
  --bg:#08090f;--s1:#0d0e1a;--s2:#111320;--s3:#161828;--s4:#1c2035;
  --brd:#202438;--brd2:#2d3254;
  --gld:#f0b429;--gld2:#d4950a;--gld-glow:rgba(240,180,41,.18);
  --ora:#ff6b35;--grn:#10d48e;--blu:#4fa3e0;--red:#f04f4f;--pur:#9f7aea;
  --txt:#dde3f0;--txt2:#8896b3;--txt3:#4a5578;
  --r:12px;--r2:8px;
  --shadow:0 4px 24px rgba(0,0,0,.5);
}
*,*::before,*::after{margin:0;padding:0;box-sizing:border-box}
html{scroll-behavior:smooth}
body{
  font-family:'DM Sans',-apple-system,BlinkMacSystemFont,sans-serif;
  background:var(--bg);color:var(--txt);min-height:100vh;overflow-x:hidden;
  font-size:15px;line-height:1.6;
}
/* Subtle grid background */
body::before{
  content:'';position:fixed;inset:0;z-index:0;pointer-events:none;
  background-image:
    radial-gradient(ellipse 60% 40% at 50% -10%,rgba(240,180,41,.07),transparent),
    linear-gradient(rgba(255,255,255,.012) 1px,transparent 1px),
    linear-gradient(90deg,rgba(255,255,255,.012) 1px,transparent 1px);
  background-size:100%,48px 48px,48px 48px;
}
.z1{position:relative;z-index:1;}

/* ── Scrollbar ── */
::-webkit-scrollbar{width:6px;}
::-webkit-scrollbar-track{background:var(--s1);}
::-webkit-scrollbar-thumb{background:var(--brd2);border-radius:3px;}

/* ── Header ── */
header{
  position:sticky;top:0;z-index:900;
  background:rgba(8,9,15,.95);backdrop-filter:blur(20px);-webkit-backdrop-filter:blur(20px);
  border-bottom:1px solid var(--brd);
  display:flex;align-items:center;gap:14px;padding:0 28px;height:52px;
}
.logo-wrap{display:flex;align-items:center;gap:10px;}
.logo{
  font-family:'Barlow Condensed',sans-serif;font-size:1.55rem;font-weight:800;letter-spacing:3px;
  background:linear-gradient(135deg,var(--gld) 20%,var(--ora));
  -webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text;
}
.logo-badge{
  font-size:.55rem;color:var(--txt3);letter-spacing:1.5px;text-transform:uppercase;
  background:var(--s3);border:1px solid var(--brd);padding:2px 7px;border-radius:4px;
}
.hdr-nav{margin-left:auto;display:flex;gap:3px;align-items:center;}
.hdr-nav a{
  color:var(--txt3);text-decoration:none;font-size:.75rem;font-weight:500;
  padding:5px 11px;border-radius:6px;border:1px solid transparent;transition:all .18s;
}
.hdr-nav a:hover{border-color:var(--brd2);color:var(--txt);}
.hdr-nav a.cta{
  background:linear-gradient(135deg,var(--gld),var(--gld2));
  color:#000;border-color:transparent;font-weight:700;
}
.hdr-nav a.cta:hover{box-shadow:0 4px 14px var(--gld-glow);transform:translateY(-1px);}

/* ── Compact hero (Part 5) ── */
.hero{
  padding:22px 20px 18px;text-align:center;
  background:radial-gradient(ellipse 70% 50% at 50% -10%,rgba(240,180,41,.07),transparent);
  border-bottom:1px solid var(--brd);
}
.hero h1{
  font-family:'Barlow Condensed',sans-serif;font-weight:800;
  font-size:clamp(1.6rem,3.8vw,2.6rem);
  letter-spacing:3px;line-height:1.05;
  background:linear-gradient(160deg,var(--gld),var(--ora) 80%);
  -webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text;
}
.hero-meta{
  display:flex;align-items:center;justify-content:center;gap:10px;
  margin-top:7px;flex-wrap:wrap;
}
.hero-tag{font-size:.68rem;color:var(--txt3);letter-spacing:.8px;}
.hero-sep{color:var(--brd2);font-size:.7rem;}
.hero-pill{
  background:rgba(240,180,41,.1);border:1px solid rgba(240,180,41,.22);
  border-radius:100px;padding:2px 11px;font-size:.62rem;color:var(--gld);
  letter-spacing:1px;text-transform:uppercase;font-weight:700;
}

/* ── Wrap ── */
.wrap{max-width:1160px;margin:0 auto;padding:22px 18px 80px;}

/* ── Section heading ── */
.sh{
  font-family:'Barlow Condensed',sans-serif;font-size:1.1rem;font-weight:700;letter-spacing:2px;
  color:var(--gld);margin-bottom:13px;display:flex;align-items:center;gap:10px;
}
.sh::after{content:'';flex:1;height:1px;background:linear-gradient(to right,var(--brd),transparent);}

/* ── Tabs ── */
.tab-bar{
  display:flex;gap:2px;background:var(--s1);border:1px solid var(--brd);
  border-radius:9px;padding:3px;width:fit-content;margin-bottom:18px;
}
.tab-btn{
  padding:6px 16px;border-radius:6px;border:none;background:transparent;
  color:var(--txt3);font-family:'DM Sans',sans-serif;font-size:.78rem;font-weight:500;
  cursor:pointer;transition:all .18s;
}
.tab-btn.active{background:var(--s3);color:var(--txt);border:1px solid var(--brd2);}

/* ── Match grid ── */
.match-grid{
  display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));
  gap:10px;margin-bottom:24px;
}
.match-card{
  background:var(--s2);border:1px solid var(--brd);border-radius:var(--r);
  padding:15px 16px 13px;cursor:pointer;transition:all .2s;position:relative;overflow:hidden;
}
.match-card::before{
  content:'';position:absolute;inset:0;
  background:linear-gradient(135deg,rgba(240,180,41,.05),transparent 60%);
  opacity:0;transition:opacity .2s;
}
.match-card:hover{border-color:rgba(240,180,41,.4);transform:translateY(-2px);box-shadow:var(--shadow);}
.match-card:hover::before{opacity:1;}
.match-card.selected{border-color:var(--gld);background:rgba(240,180,41,.05);box-shadow:0 0 0 1px var(--gld),var(--shadow);}
.match-time{
  position:absolute;top:10px;right:10px;
  background:rgba(240,180,41,.12);border:1px solid rgba(240,180,41,.22);
  color:var(--gld);font-size:.56rem;font-weight:700;padding:2px 7px;border-radius:100px;
}
.match-id-tag{font-size:.6rem;color:var(--txt3);letter-spacing:.8px;text-transform:uppercase;margin-bottom:7px;}
.match-vs{
  font-family:'Barlow Condensed',sans-serif;font-size:1.5rem;font-weight:700;letter-spacing:1px;
  text-align:center;line-height:1;
}
.match-vs em{color:var(--gld);font-style:normal;margin:0 7px;font-size:.85rem;font-weight:400;}
.match-venue{font-size:.63rem;color:var(--txt3);text-align:center;margin-top:5px;}

/* ── Mode cards ── */
.mode-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin-bottom:24px;}
@media(max-width:560px){.mode-grid{grid-template-columns:1fr;}}
.mode-card{
  border-radius:var(--r);padding:18px 14px;text-align:center;
  cursor:pointer;border:2px solid transparent;transition:all .22s;position:relative;overflow:hidden;
}
.mode-card::after{content:'';position:absolute;inset:0;opacity:0;transition:opacity .22s;
  background:radial-gradient(ellipse at top,rgba(255,255,255,.04),transparent);}
.mode-card:hover::after{opacity:1;}
.mode-card.safe{background:linear-gradient(145deg,#05120e,#071510);border-color:rgba(16,212,142,.2);}
.mode-card.balanced{background:linear-gradient(145deg,#05101e,#071525);border-color:rgba(79,163,224,.2);}
.mode-card.risky{background:linear-gradient(145deg,#140508,#1a0608);border-color:rgba(240,79,79,.2);}
.mode-card:hover{transform:translateY(-3px);}
.mode-card.active.safe{border-color:var(--grn);box-shadow:0 0 30px rgba(16,212,142,.15);}
.mode-card.active.balanced{border-color:var(--blu);box-shadow:0 0 30px rgba(79,163,224,.15);}
.mode-card.active.risky{border-color:var(--red);box-shadow:0 0 30px rgba(240,79,79,.15);}
.mode-icon{font-size:1.8rem;margin-bottom:7px;}
.mode-name{font-family:'Barlow Condensed',sans-serif;font-size:1.3rem;font-weight:700;letter-spacing:2px;}
.mode-card.safe .mode-name{color:var(--grn);}
.mode-card.balanced .mode-name{color:var(--blu);}
.mode-card.risky .mode-name{color:var(--red);}
.mode-desc{font-size:.68rem;color:var(--txt3);margin-top:4px;line-height:1.45;}
.mode-note{font-size:.6rem;margin-top:6px;padding:2px 8px;border-radius:5px;display:inline-block;font-weight:600;}
.mode-card.safe .mode-note{background:rgba(16,212,142,.1);color:var(--grn);}
.mode-card.balanced .mode-note{background:rgba(79,163,224,.1);color:var(--blu);}
.mode-card.risky .mode-note{background:rgba(240,79,79,.1);color:var(--red);}

/* ── Advanced Criteria (Part 3) ── */
.adv-section{background:var(--s2);border:1px solid var(--brd);border-radius:var(--r);padding:20px;margin-bottom:22px;}
.adv-group{margin-bottom:18px;}
.adv-group:last-child{margin-bottom:0;}
.adv-group-title{
  font-family:'Barlow Condensed',sans-serif;font-size:.85rem;font-weight:700;letter-spacing:1.5px;
  color:var(--txt3);text-transform:uppercase;margin-bottom:10px;
  padding-bottom:6px;border-bottom:1px solid var(--brd);
}
.crit-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(235px,1fr));gap:6px;}
.crit-item{
  background:var(--s3);border:1px solid var(--brd);border-radius:var(--r2);
  padding:8px 12px;display:flex;align-items:flex-start;gap:9px;cursor:pointer;
  transition:border-color .16s,background .16s;
}
.crit-item:hover{border-color:rgba(240,180,41,.3);background:var(--s4);}
.crit-item input[type="checkbox"]{
  accent-color:var(--gld);width:14px;height:14px;flex-shrink:0;cursor:pointer;margin-top:2px;
}
.crit-item label{font-size:.72rem;color:var(--txt);cursor:pointer;line-height:1.35;user-select:none;}

/* Inputs row */
.input-row{display:flex;gap:12px;flex-wrap:wrap;margin-bottom:16px;}
.input-group{flex:1;min-width:130px;display:flex;flex-direction:column;gap:5px;}
.input-group label{font-size:.63rem;color:var(--txt3);letter-spacing:.9px;text-transform:uppercase;font-weight:600;}
.input-group input,.input-group select{
  background:var(--s3);border:1px solid var(--brd);border-radius:var(--r2);
  padding:8px 11px;color:var(--txt);font-size:.82rem;
  font-family:'DM Sans',sans-serif;width:100%;transition:border-color .16s;outline:none;
}
.input-group input:focus,.input-group select:focus{
  border-color:rgba(240,180,41,.45);box-shadow:0 0 0 3px rgba(240,180,41,.07);
}

/* ── Buttons ── */
.btn{
  display:inline-flex;align-items:center;justify-content:center;gap:7px;padding:10px 22px;
  border-radius:var(--r2);border:none;cursor:pointer;
  font-family:'Barlow Condensed',sans-serif;font-size:1rem;font-weight:700;letter-spacing:1.5px;
  text-decoration:none;transition:all .2s;white-space:nowrap;
}
.btn-gold{background:linear-gradient(135deg,var(--gld),var(--gld2));color:#000;}
.btn-gold:hover{transform:translateY(-2px);box-shadow:0 8px 22px var(--gld-glow);}
.btn-ora{background:linear-gradient(135deg,var(--ora),#d84000);color:#fff;}
.btn-ora:hover{transform:translateY(-2px);box-shadow:0 8px 22px rgba(255,107,53,.3);}
.btn-grn{background:linear-gradient(135deg,var(--grn),#0aad74);color:#000;}
.btn-grn:hover{transform:translateY(-2px);box-shadow:0 8px 22px rgba(16,212,142,.25);}
.btn-ghost{background:transparent;color:var(--txt3);border:1px solid var(--brd);}
.btn-ghost:hover{border-color:var(--brd2);color:var(--txt);}
.btn-row{display:flex;gap:10px;flex-wrap:wrap;margin-bottom:28px;align-items:center;}
.btn-lg{padding:13px 30px;font-size:1.1rem;border-radius:10px;}

/* Alert */
.alert-sel{
  background:rgba(240,180,41,.07);border:1px solid rgba(240,180,41,.22);
  border-radius:var(--r2);padding:9px 13px;font-size:.78rem;color:var(--txt2);
  margin-bottom:14px;display:none;
}

.divider{height:1px;background:var(--brd);margin:22px 0;}

/* ── Results: match strip ── */
.match-strip{
  background:var(--s2);border:1px solid var(--brd);border-radius:var(--r);
  padding:14px 20px;margin-bottom:18px;display:flex;align-items:center;gap:14px;flex-wrap:wrap;
}
.strip-vs{font-family:'Barlow Condensed',sans-serif;font-size:1.5rem;font-weight:700;letter-spacing:1.5px;line-height:1;}
.strip-vs em{color:var(--gld);font-style:normal;margin:0 8px;}
.strip-venue{font-size:.65rem;color:var(--txt3);margin-top:3px;}
.strip-right{margin-left:auto;display:flex;gap:7px;flex-wrap:wrap;align-items:center;}
.pill{padding:3px 11px;border-radius:100px;font-size:.66rem;font-weight:700;
  text-transform:uppercase;letter-spacing:.8px;border:1px solid transparent;}
.pill-safe{background:rgba(16,212,142,.1);color:var(--grn);border-color:rgba(16,212,142,.22);}
.pill-balanced{background:rgba(79,163,224,.1);color:var(--blu);border-color:rgba(79,163,224,.22);}
.pill-risky{background:rgba(240,79,79,.1);color:var(--red);border-color:rgba(240,79,79,.22);}
.pill-neutral{background:var(--s3);color:var(--txt3);border-color:var(--brd);}

/* Stats bar */
.stats-bar{display:flex;gap:9px;flex-wrap:wrap;margin-bottom:18px;}
.stat-chip{background:var(--s2);border:1px solid var(--brd);border-radius:10px;padding:8px 15px;text-align:center;}
.stat-chip strong{display:block;font-size:1.05rem;font-weight:700;color:var(--gld);line-height:1;}
.stat-chip span{font-size:.6rem;color:var(--txt3);text-transform:uppercase;letter-spacing:.5px;}

/* ── Team grid ── */
.res-topbar{display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:10px;margin-bottom:16px;}
.team-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(290px,1fr));gap:14px;}

.team-card{
  background:var(--s2);border:1px solid var(--brd);border-radius:var(--r);
  overflow:hidden;position:relative;transition:border-color .18s,transform .2s,box-shadow .2s;
}
.team-card:hover{border-color:var(--brd2);transform:translateY(-1px);box-shadow:var(--shadow);}

.team-hdr{
  background:linear-gradient(135deg,#0d1525,#0a1020);
  padding:10px 14px;display:flex;justify-content:space-between;align-items:center;
  border-bottom:1px solid var(--brd);
}
.team-num{font-family:'Barlow Condensed',sans-serif;font-size:.92rem;font-weight:700;color:var(--gld);letter-spacing:2px;}
.badge{font-size:.56rem;font-weight:700;padding:2px 8px;border-radius:100px;letter-spacing:.8px;text-transform:uppercase;}
.badge-free{background:var(--grn);color:#000;}
.badge-lock{background:var(--s4);color:var(--txt3);border:1px solid var(--brd2);}

.cv-row{display:flex;gap:6px;padding:10px 12px 0;}
.cv-pill{flex:1;background:var(--s3);border:1px solid var(--brd);border-radius:var(--r2);padding:6px 8px;text-align:center;}
.cv-lbl{display:block;font-size:.56rem;color:var(--txt3);letter-spacing:.4px;text-transform:uppercase;font-weight:600;margin-bottom:2px;}
.cv-nm{font-size:.75rem;font-weight:600;display:block;line-height:1.25;}
.cv-c .cv-nm{color:var(--gld);}
.cv-vc .cv-nm{color:var(--blu);}

.plist{list-style:none;padding:8px 12px 0;}
.pitem{
  display:flex;align-items:center;gap:6px;
  padding:4.5px 0;border-bottom:1px solid rgba(32,36,56,.8);font-size:.73rem;
}
.pitem:last-child{border-bottom:none;}
.rdot{width:5px;height:5px;border-radius:50%;flex-shrink:0;}
.d-bat{background:var(--blu);}.d-bowl{background:var(--ora);}
.d-ar{background:var(--grn);}.d-wk{background:var(--gld);}
.pname{flex:1;color:var(--txt);}
.ct{color:var(--gld);font-size:.6rem;font-weight:700;margin-left:3px;}
.vct{color:var(--blu);font-size:.6rem;font-weight:700;margin-left:3px;}
.rtag{font-size:.56rem;font-weight:600;padding:1px 6px;border-radius:5px;flex-shrink:0;}
.rL{background:rgba(16,212,142,.1);color:var(--grn);}
.rM{background:rgba(79,163,224,.1);color:var(--blu);}
.rH{background:rgba(240,79,79,.1);color:var(--red);}

.card-foot{
  padding:8px 12px;border-top:1px solid var(--brd);margin-top:8px;
  display:flex;justify-content:space-between;align-items:center;
}
.foot-info{font-size:.6rem;color:var(--txt3);}
.copy-btn{
  background:none;border:1px solid var(--brd);color:var(--txt3);
  font-size:.65rem;padding:3px 10px;border-radius:5px;cursor:pointer;
  transition:all .16s;font-family:'DM Sans',sans-serif;font-weight:500;
}
.copy-btn:hover:not(:disabled){border-color:var(--gld);color:var(--gld);}
.copy-btn:disabled{opacity:.22;cursor:default;}

/* ── Lock overlay ── */
.lock-ov{
  position:absolute;inset:0;background:rgba(8,9,15,.85);
  backdrop-filter:blur(5px);-webkit-backdrop-filter:blur(5px);
  border-radius:var(--r);z-index:20;
  display:flex;flex-direction:column;align-items:center;justify-content:center;gap:6px;
}
.lock-ico{font-size:1.8rem;}.lock-lbl{font-family:'Barlow Condensed',sans-serif;font-size:.95rem;font-weight:700;letter-spacing:2px;color:var(--txt3);}
.lock-sub{font-size:.6rem;color:var(--txt3);}

/* ── PART 1: Unlock Banner — placed AFTER first 3, BEFORE locked teams ── */
.unlock-banner{
  background:linear-gradient(135deg,rgba(17,13,2,.9),rgba(26,20,4,.9));
  border:2px solid rgba(240,180,41,.28);border-radius:14px;
  padding:24px 28px;text-align:center;
  position:relative;overflow:hidden;
  grid-column:1/-1;  /* span full grid width */
}
.unlock-banner::before{
  content:'';position:absolute;inset:0;
  background:radial-gradient(ellipse at top,rgba(240,180,41,.06),transparent 70%);
  pointer-events:none;
}
.unlock-banner h3{
  font-family:'Barlow Condensed',sans-serif;font-size:1.55rem;font-weight:800;letter-spacing:2px;
  color:var(--gld);margin-bottom:4px;position:relative;
}
.unlock-banner p{color:var(--txt3);font-size:.78rem;margin-bottom:14px;position:relative;}
.unlock-banner .btn{position:relative;}

/* ── Ad Modal (Part 2 — FIXED) ── */
.modal-bg{
  position:fixed;inset:0;background:rgba(0,0,0,.94);z-index:9000;
  display:flex;align-items:center;justify-content:center;
  opacity:0;pointer-events:none;transition:opacity .25s;
}
.modal-bg.open{opacity:1;pointer-events:all;}
.modal-box{
  background:var(--s2);border:2px solid rgba(240,180,41,.28);border-radius:16px;
  padding:32px 36px;max-width:390px;width:92%;text-align:center;
  transform:scale(.95);transition:transform .25s;
}
.modal-bg.open .modal-box{transform:scale(1);}
.modal-box h2{
  font-family:'Barlow Condensed',sans-serif;font-size:1.7rem;font-weight:800;letter-spacing:2px;
  color:var(--gld);margin-bottom:5px;
}
.modal-box > p{color:var(--txt3);font-size:.78rem;margin-bottom:16px;}
.ad-box{
  background:var(--s1);border:2px dashed var(--brd2);border-radius:11px;
  padding:22px 18px;margin:16px 0;
}
.ad-icon{font-size:2.4rem;margin-bottom:6px;}
.ad-label{font-size:.83rem;color:var(--txt2);font-weight:600;}
.ad-sub{font-size:.66rem;color:var(--txt3);margin-top:2px;}
.ad-prog{height:6px;background:var(--brd);border-radius:100px;overflow:hidden;margin-top:14px;}
.ad-bar{height:100%;background:linear-gradient(90deg,var(--ora),var(--gld));border-radius:100px;width:0%;transition:width .08s linear;}
.ad-tmr{font-size:1.1rem;font-weight:700;color:var(--ora);margin-top:10px;letter-spacing:1px;}
.modal-close-note{font-size:.65rem;color:var(--txt3);margin-top:10px;}

/* Toast */
.toast{
  position:fixed;bottom:22px;right:22px;z-index:9999;
  padding:10px 18px;border-radius:9px;font-size:.78rem;font-weight:600;
  transform:translateY(50px);opacity:0;transition:all .28s;pointer-events:none;
  box-shadow:var(--shadow);
}
.toast.show{transform:translateY(0);opacity:1;}

/* ── Content sections ── */
.content-section{max-width:820px;margin:44px auto 0;padding:0 18px;}
.content-section h2{
  font-family:'Barlow Condensed',sans-serif;font-size:1.45rem;font-weight:700;letter-spacing:2px;
  color:var(--gld);margin-bottom:13px;
}
.content-section h3{
  font-family:'Barlow Condensed',sans-serif;font-size:1.05rem;font-weight:700;letter-spacing:1.5px;
  color:var(--txt);margin:18px 0 7px;
}
.content-section p{color:var(--txt2);font-size:.87rem;line-height:1.7;margin-bottom:11px;}
.content-section ul,.content-section ol{
  color:var(--txt2);font-size:.87rem;line-height:1.7;padding-left:1.4em;margin-bottom:11px;
}
.content-section li{margin-bottom:5px;}
.content-section a{color:var(--gld);text-decoration:none;}
.content-section a:hover{text-decoration:underline;}

/* FAQ */
.faq-item{
  background:var(--s2);border:1px solid var(--brd);border-radius:10px;
  margin-bottom:7px;overflow:hidden;
}
.faq-q{
  padding:12px 15px;cursor:pointer;font-size:.83rem;font-weight:600;
  color:var(--txt);display:flex;justify-content:space-between;align-items:center;
  transition:background .16s;
}
.faq-q:hover{background:var(--s3);}
.faq-q .arrow{color:var(--gld);font-size:1rem;transition:transform .2s;flex-shrink:0;margin-left:12px;}
.faq-q.open .arrow{transform:rotate(180deg);}
.faq-a{
  padding:0 15px;max-height:0;overflow:hidden;transition:max-height .3s ease,padding .3s;
  font-size:.8rem;color:var(--txt2);line-height:1.65;
}
.faq-a.open{max-height:350px;padding:0 15px 13px;}

/* Footer */
footer{
  background:var(--s1);border-top:1px solid var(--brd);
  padding:32px 28px 22px;margin-top:56px;
}
.footer-grid{
  max-width:1160px;margin:0 auto;
  display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:24px;
  margin-bottom:24px;
}
.footer-col h4{
  font-family:'Barlow Condensed',sans-serif;font-size:.95rem;font-weight:700;letter-spacing:1.5px;
  color:var(--gld);margin-bottom:9px;
}
.footer-col p,.footer-col a{
  font-size:.73rem;color:var(--txt3);display:block;margin-bottom:4px;
  text-decoration:none;transition:color .16s;line-height:1.5;
}
.footer-col a:hover{color:var(--txt);}
.footer-bottom{
  max-width:1160px;margin:0 auto;padding-top:18px;
  border-top:1px solid var(--brd);
  display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:9px;
}
.footer-bottom p{font-size:.68rem;color:var(--txt3);}
.footer-disclaimer{
  font-size:.66rem;color:var(--txt3);line-height:1.5;
  max-width:1160px;margin:14px auto 0;text-align:center;
}

/* Legal pages */
.legal-wrap{max-width:800px;margin:0 auto;padding:38px 20px 80px;}
.legal-wrap h1{
  font-family:'Barlow Condensed',sans-serif;font-size:1.9rem;font-weight:800;letter-spacing:3px;
  color:var(--gld);margin-bottom:5px;
}
.legal-wrap .last-updated{font-size:.7rem;color:var(--txt3);margin-bottom:26px;}
.legal-wrap h2{font-size:1rem;font-weight:700;color:var(--txt);margin:22px 0 7px;}
.legal-wrap p{font-size:.84rem;color:var(--txt2);line-height:1.7;margin-bottom:11px;}
.legal-wrap ul{font-size:.84rem;color:var(--txt2);line-height:1.7;padding-left:1.4em;margin-bottom:11px;}
.legal-wrap li{margin-bottom:4px;}
.legal-wrap a{color:var(--gld);text-decoration:none;}

/* Contact form */
.contact-form{display:flex;flex-direction:column;gap:13px;max-width:540px;}
.form-group{display:flex;flex-direction:column;gap:5px;}
.form-group label{font-size:.7rem;color:var(--txt3);letter-spacing:.8px;text-transform:uppercase;font-weight:600;}
.form-group input,.form-group textarea,.form-group select{
  background:var(--s2);border:1px solid var(--brd);border-radius:var(--r2);
  padding:9px 12px;color:var(--txt);font-size:.83rem;font-family:'DM Sans',sans-serif;
  outline:none;transition:border-color .16s;
}
.form-group input:focus,.form-group textarea:focus{
  border-color:rgba(240,180,41,.45);box-shadow:0 0 0 3px rgba(240,180,41,.07);
}
.form-group textarea{resize:vertical;min-height:110px;}
.form-msg{background:rgba(16,212,142,.1);border:1px solid rgba(16,212,142,.28);border-radius:var(--r2);padding:11px 15px;font-size:.8rem;color:var(--grn);display:none;}

/* About cards */
.about-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(210px,1fr));gap:12px;margin:18px 0;}
.about-card{background:var(--s2);border:1px solid var(--brd);border-radius:var(--r);padding:18px 15px;text-align:center;}
.about-icon{font-size:2rem;margin-bottom:9px;}
.about-card h3{font-size:.88rem;font-weight:700;color:var(--txt);margin-bottom:5px;}
.about-card p{font-size:.74rem;color:var(--txt3);line-height:1.5;}

/* Age bar */
.age-bar{
  background:rgba(240,79,79,.08);border:1px solid rgba(240,79,79,.2);
  border-radius:var(--r2);padding:7px 13px;font-size:.72rem;color:var(--red);
  text-align:center;margin-bottom:14px;
}

/* Section spacing helpers */
.mb-4{margin-bottom:16px;} .mb-6{margin-bottom:24px;} .mt-4{margin-top:16px;}

/* Animations */
@keyframes fadeUp{from{opacity:0;transform:translateY(14px);}to{opacity:1;transform:translateY(0);}}
.fade-up{animation:fadeUp .35s ease both;}

/* Print */
@media print{
  header,nav,.unlock-banner,.btn,.copy-btn,.lock-ov,.modal-bg,.toast,footer,
  .content-section,.tab-bar,.age-bar{display:none!important;}
  body{background:#fff;color:#000;}
  .team-card{border:1px solid #ccc;break-inside:avoid;background:#fff;}
  .team-hdr{background:#f5f5f5;}
  .pname{color:#000;}.cv-nm{color:#b8860b!important;}
}

/* Mobile */
@media(max-width:480px){
  header{padding:0 14px;}
  .wrap{padding:16px 12px 60px;}
  .match-grid{grid-template-columns:1fr;}
  .mode-grid{grid-template-columns:1fr;}
  .input-row{flex-direction:column;}
  .team-grid{grid-template-columns:1fr;}
  .modal-box{padding:24px 20px;}
}
</style>
<script async src="https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client=ca-pub-9904803540658016"
     crossorigin="anonymous"></script>
"""

# ─── Footer ───────────────────────────────────────────────────────────────────

_FOOTER = """
<footer>
  <div class="footer-grid">
    <div class="footer-col">
      <h4>⚡ FantasyXI</h4>
      <p>India's smart fantasy cricket team generator for the ICC T20 World Cup 2026 Super 8s. Generate 20 unique, optimised teams in seconds.</p>
      <p style="margin-top:8px;">📧 <a href="mailto:contact@fantasyxi.in">contact@fantasyxi.in</a></p>
    </div>
    <div class="footer-col">
      <h4>Quick Links</h4>
      <a href="/">🏠 Home / Generator</a>
      <a href="/about">ℹ️ About Us</a>
      <a href="/how-it-works">📖 How It Works</a>
      <a href="/contact">✉️ Contact Us</a>
    </div>
    <div class="footer-col">
      <h4>Legal</h4>
      <a href="/privacy">🔒 Privacy Policy</a>
      <a href="/terms">📋 Terms &amp; Conditions</a>
      <a href="/disclaimer">⚠️ Disclaimer</a>
    </div>
    <div class="footer-col">
      <h4>Compliance</h4>
      <p>This website uses cookies and may display third-party advertisements. By using this site, you agree to our <a href="/privacy">Privacy Policy</a> and <a href="/terms">Terms</a>.</p>
      <p style="margin-top:6px;">🔞 For users 18+ only.</p>
    </div>
  </div>
  <div class="footer-bottom">
    <p>© 2026 FantasyXI. All rights reserved. Not affiliated with ICC, BCCI, or any official cricket body.</p>
    <p>Built for entertainment &amp; informational purposes only.</p>
  </div>
  <div class="footer-disclaimer">
    ⚠️ Fantasy sports involve financial risk. Please play responsibly. FantasyXI does not guarantee any winnings. Check local laws before participating in paid fantasy sports contests.
  </div>
</footer>
"""

# ─── Ad Modal (Part 2 — FIXED) ────────────────────────────────────────────────

_AD_MODAL = """
<div class="modal-bg" id="adModal" aria-modal="true" role="dialog">
  <div class="modal-box">
    <h2>📺 Simulated Ad</h2>
    <p>Watch this 5-second ad to unlock all remaining teams</p>
    <div class="ad-box">
      <div class="ad-icon">🎬</div>
      <div class="ad-label">Advertisement</div>
      <div class="ad-sub">Simulated · No real SDK required</div>
      <div class="ad-prog"><div class="ad-bar" id="adBar"></div></div>
      <div class="ad-tmr" id="adTmr">⏳ 5s remaining</div>
    </div>
    <p class="modal-close-note" id="closeNote">Please wait for the ad to finish…</p>
  </div>
</div>
<div class="toast" id="toast"></div>
"""

# ─── Shared JS ────────────────────────────────────────────────────────────────

_SHARED_JS = """
<script>
/* ─ Toast ─ */
function showToast(msg, color) {
  color = color || '#10d48e';
  var t = document.getElementById('toast');
  if (!t) return;
  t.textContent = msg; t.style.background = color;
  t.style.color = (color === '#10d48e' || color === '#f0b429') ? '#000' : '#fff';
  t.classList.add('show');
  setTimeout(function(){ t.classList.remove('show'); }, 3200);
}

/* ─ Smooth scroll (Part 4) ─ */
function scrollTo(id) {
  var el = document.getElementById(id);
  if (el) { el.scrollIntoView({ behavior: 'smooth', block: 'start' }); }
}

/* ─ FAQ toggle ─ */
function toggleFaq(el) {
  var a = el.nextElementSibling;
  var isOpen = el.classList.contains('open');
  document.querySelectorAll('.faq-q').forEach(function(q) {
    q.classList.remove('open');
    if (q.nextElementSibling) q.nextElementSibling.classList.remove('open');
  });
  if (!isOpen) { el.classList.add('open'); a.classList.add('open'); }
}

/* ─ Ad / unlock (Part 2 — FIXED) ─ */
var adInterval = null;
var adCountdown = 5;

function openAd() {
  var modal = document.getElementById('adModal');
  if (!modal) return;
  modal.classList.add('open');
  adCountdown = 5;
  var bar = document.getElementById('adBar');
  var tmr = document.getElementById('adTmr');
  var note = document.getElementById('closeNote');
  if (bar) bar.style.width = '0%';
  if (tmr) tmr.textContent = '⏳ 5s remaining';
  if (note) note.textContent = 'Please wait for the ad to finish…';

  // Clear any existing interval
  if (adInterval) clearInterval(adInterval);

  adInterval = setInterval(function() {
    adCountdown--;
    var pct = ((5 - adCountdown) / 5 * 100).toFixed(1);
    if (bar) bar.style.width = pct + '%';
    if (tmr) {
      if (adCountdown > 0) {
        tmr.textContent = '⏳ ' + adCountdown + 's remaining';
      } else {
        tmr.textContent = '✅ Complete!';
        if (note) note.textContent = 'Unlocking your teams…';
      }
    }
    if (adCountdown <= 0) {
      clearInterval(adInterval);
      adInterval = null;
      setTimeout(function() {
        modal.classList.remove('open');
        doUnlock();
      }, 700);
    }
  }, 1000);
}

function doUnlock() {
  fetch('/unlock', { method: 'POST' })
    .then(function(r) { return r.json(); })
    .then(function(d) {
      if (!d.success) { showToast('Error unlocking. Please try again.', '#f04f4f'); return; }
      // Remove all lock overlays with animation
      document.querySelectorAll('.lock-ov').forEach(function(el) {
        el.style.transition = 'opacity .45s ease';
        el.style.opacity = '0';
        setTimeout(function() { el.remove(); }, 450);
      });
      // Enable all copy buttons
      document.querySelectorAll('.copy-btn').forEach(function(b) { b.disabled = false; });
      // Update badge on locked cards
      document.querySelectorAll('.badge-lock').forEach(function(b) {
        b.textContent = '✓ UNLOCKED'; b.classList.remove('badge-lock'); b.classList.add('badge-free');
      });
      // Update unlock banner
      var banner = document.getElementById('unlockBanner');
      if (banner) {
        banner.innerHTML = '<h3 style="color:var(--grn);position:relative;">✅ All Teams Unlocked!</h3>'
          + '<p style="position:relative;color:var(--txt2);">All ' + document.querySelectorAll('.team-card').length + ' teams are now available.</p>'
          + '<div style="position:relative;margin-top:4px;">'
          + '<a href="/export_pdf" class="btn btn-grn btn-lg">📄 Export All Teams as PDF</a></div>';
      }
      // Show PDF button in header
      var pBtn = document.getElementById('pdfBtn');
      if (pBtn) pBtn.style.display = 'inline-flex';
      showToast('🎉 All teams unlocked!', '#f0b429');
    })
    .catch(function() { showToast('Network error. Please retry.', '#f04f4f'); });
}

/* ─ Copy team ─ */
function copyTeam(idx) {
  var cards = document.querySelectorAll('.team-card');
  var card = cards[idx];
  if (!card) return;
  var num = card.querySelector('.team-num') ? card.querySelector('.team-num').textContent : '';
  var nms = card.querySelectorAll('.cv-nm');
  var cap = nms[0] ? nms[0].textContent.trim() : '';
  var vc  = nms[1] ? nms[1].textContent.trim() : '';
  var txt = num + '\\nCaptain (2x): ' + cap + '\\nVC (1.5x): ' + vc + '\\n\\nPlayers:\\n';
  card.querySelectorAll('.pname').forEach(function(s) {
    txt += s.textContent.replace(/\\s+/g, ' ').trim() + '\\n';
  });
  if (navigator.clipboard) {
    navigator.clipboard.writeText(txt).then(function() { showToast('📋 Team ' + (idx + 1) + ' copied!'); });
  } else {
    var ta = document.createElement('textarea');
    ta.value = txt; document.body.appendChild(ta); ta.select();
    document.execCommand('copy'); document.body.removeChild(ta);
    showToast('📋 Team ' + (idx + 1) + ' copied!');
  }
}
</script>
"""

# ─── HOME PAGE ────────────────────────────────────────────────────────────────

HOME_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<title>FantasyXI — ICC T20 WC 2026 Super 8s Fantasy Team Generator</title>
<meta name="description" content="Generate 20 unique fantasy cricket teams for ICC T20 World Cup 2026 Super 8s. Smart distribution engine with Safe, Balanced and Risky modes. Free team generator.">
<meta name="keywords" content="fantasy cricket, T20 World Cup 2026, fantasy team generator, ICC Super 8s, dream11 teams, fantasy XI, cricket team generator">
<meta name="robots" content="index, follow">
<meta property="og:title" content="FantasyXI — ICC T20 WC 2026 Fantasy Team Generator">
<meta property="og:description" content="Generate 20 unique optimised fantasy cricket teams for Super 8s matches. 100% free.">
<meta property="og:type" content="website">
<link rel="canonical" href="https://fantasyxi.in/">
""" + _CSS + """
</head>
<body>

<header>
  <div class="logo-wrap">
    <div>
      <div class="logo">⚡ FantasyXI</div>
    </div>
    <span class="logo-badge">Super 8s · T20 WC 2026</span>
  </div>
  <nav class="hdr-nav">
    <a href="/about">About</a>
    <a href="/how-it-works">How It Works</a>
    <a href="/privacy">Privacy</a>
    <a href="#tool" class="cta">Generate →</a>
  </nav>
</header>

<!-- Part 5: Compact hero -->
<div class="hero z1" id="top">
  <h1>ICC T20 WC 2026 · Fantasy Team Generator</h1>
  <div class="hero-meta">
    <span class="hero-tag">⚡ 20 unique teams</span>
    <span class="hero-sep">·</span>
    <span class="hero-tag">3 risk modes</span>
    <span class="hero-sep">·</span>
    <span class="hero-tag">Smart distribution engine</span>
    <span class="hero-pill">🏆 Super 8s Edition</span>
  </div>
</div>

<div class="wrap z1" id="tool">

  <div class="age-bar">⚠️ This tool is intended for users aged 18 and above. Fantasy sports may involve financial risk in paid contests. Play responsibly.</div>

  <!-- Tabs -->
  <div class="tab-bar">
    <button class="tab-btn active" onclick="showTab('up', this)">📅 Upcoming Matches</button>
    <button class="tab-btn" onclick="showTab('man', this)">⚙ Manual Selection</button>
  </div>

  <!-- UPCOMING -->
  <div id="tab-up">
    <div class="sh">Select a Match</div>
    <div class="match-grid">
    {% for m in matches %}
      <div class="match-card" onclick="selectMatch('{{m.match_id}}','{{m.team1}}','{{m.team2}}','{{m.date}}','{{m.venue|replace(\"'\",\"\")}}', this)">
        <div class="match-time">{{m.time}}</div>
        <div class="match-id-tag">📅 {{m.date}} · {{m.match_id}}</div>
        <div class="match-vs">{{m.team1}}<em>VS</em>{{m.team2}}</div>
        <div class="match-venue">📍 {{m.venue}}</div>
      </div>
    {% endfor %}
    </div>
    <div class="alert-sel" id="selInfo"></div>
  </div>

  <!-- MANUAL -->
  <div id="tab-man" style="display:none;">
    <div class="sh">Manual Team Selection</div>
    <div class="input-row">
      <div class="input-group"><label>Team 1</label>
        <select id="mt1">{% for t in all_teams %}<option value="{{t.team}}">{{t.team}}</option>{% endfor %}</select>
      </div>
      <div class="input-group"><label>Team 2</label>
        <select id="mt2">{% for t in all_teams %}<option value="{{t.team}}"{% if loop.index==2 %} selected{% endif %}>{{t.team}}</option>{% endfor %}</select>
      </div>
    </div>
    <button class="btn btn-ghost" onclick="setManual()">Confirm Teams →</button>
  </div>

  <div class="divider"></div>

  <!-- Part 4: Mode section — scroll target -->
  <div id="section-mode">
    <div class="sh">Generation Mode</div>
    <div class="mode-grid">
      <div class="mode-card safe" onclick="selectMode('safe', this)">
        <div class="mode-icon">🛡</div>
        <div class="mode-name">Safe</div>
        <div class="mode-desc">Low-risk captains · Conservative stable picks</div>
        <div class="mode-note">Best for small contests</div>
      </div>
      <div class="mode-card balanced" onclick="selectMode('balanced', this)">
        <div class="mode-icon">⚖️</div>
        <div class="mode-name">Balanced</div>
        <div class="mode-desc">Mixed risk · Smart C/VC rotation</div>
        <div class="mode-note">Best for mid-size contests</div>
      </div>
      <div class="mode-card risky" onclick="selectMode('risky', this)">
        <div class="mode-icon">🔥</div>
        <div class="mode-name">Risky</div>
        <div class="mode-desc">High-risk differentials · Max points ceiling</div>
        <div class="mode-note">Best for mega contests</div>
      </div>
    </div>
  </div>

  <!-- Part 3: Advanced Criteria — scroll target -->
  <div id="section-criteria">
    <div class="sh">Advanced Criteria</div>

    <div class="adv-section">

      <!-- Group 1: Basic settings -->
      <div class="adv-group">
        <div class="adv-group-title">⚙️ Generation Settings</div>
        <div class="input-row">
          <div class="input-group">
            <label>Teams to Generate (max 20)</label>
            <input type="number" id="nt" value="20" min="5" max="20">
          </div>
          <div class="input-group">
            <label>Player Exposure Limit (%)</label>
            <input type="number" id="exposure" value="75" min="10" max="100"
              title="Max % of teams a single player can appear in">
          </div>
          <div class="input-group">
            <label>Max Players from One Team</label>
            <input type="number" id="max_from_one" value="7" min="5" max="10">
          </div>
        </div>
      </div>

      <!-- Group 2: Captain/VC controls -->
      <div class="adv-group">
        <div class="adv-group-title">👑 Captain &amp; Vice-Captain Rules</div>
        <div class="crit-grid">
          <label class="crit-item">
            <input type="checkbox" id="c6" checked>
            <span>At least 5 unique C/VC combinations</span>
          </label>
          <label class="crit-item">
            <input type="checkbox" id="c7" checked>
            <span>Avoid same C/VC pair repeating</span>
          </label>
          <label class="crit-item">
            <input type="checkbox" id="c8" checked>
            <span>Risk-based captain weighting</span>
          </label>
          <label class="crit-item">
            <input type="checkbox" id="c11" checked>
            <span>Captain must not repeat &gt;3 consecutive</span>
          </label>
          <label class="crit-item">
            <input type="checkbox" id="c15" checked>
            <span>≥1 All-rounder captain in first 5 teams</span>
          </label>
          <label class="crit-item">
            <input type="checkbox" id="unique_cap">
            <span>Unique captain for each team</span>
          </label>
          <label class="crit-item">
            <input type="checkbox" id="unique_vc">
            <span>Unique vice-captain for each team</span>
          </label>
        </div>
      </div>

      <!-- Group 3: Team composition -->
      <div class="adv-group">
        <div class="adv-group-title">🏏 Team Composition Rules</div>
        <div class="crit-grid">
          <label class="crit-item">
            <input type="checkbox" id="c1" checked>
            <span>Balanced 6:5 team-split rotation</span>
          </label>
          <label class="crit-item">
            <input type="checkbox" id="c12" checked>
            <span>No identical team combination</span>
          </label>
          <label class="crit-item">
            <input type="checkbox" id="c13" checked>
            <span>Max players from one team limit</span>
          </label>
          <label class="crit-item">
            <input type="checkbox" id="c14" checked>
            <span>Role constraints (WK/BAT/AR/BOWL)</span>
          </label>
          <label class="crit-item">
            <input type="checkbox" id="balanced_dist">
            <span>Balanced team distribution toggle</span>
          </label>
          <label class="crit-item">
            <input type="checkbox" id="differential">
            <span>Differential player inclusion (last 10 teams)</span>
          </label>
        </div>
      </div>

      <!-- Group 4: Player controls -->
      <div class="adv-group">
        <div class="adv-group-title">🎯 Player Controls</div>
        <div class="input-row">
          <div class="input-group">
            <label>Lock Players (comma-separated IDs)</label>
            <input type="text" id="locked_players" placeholder="e.g. T1-P1, T2-P3">
          </div>
          <div class="input-group">
            <label>Exclude Players (comma-separated IDs)</label>
            <input type="text" id="excluded_players" placeholder="e.g. T1-P6, T2-P9">
          </div>
        </div>
        <p style="font-size:.68rem;color:var(--txt3);margin-top:-6px;">Player IDs are shown in the team preview. Locked players appear in every team. Excluded players are never selected.</p>
      </div>

    </div><!-- /adv-section -->

    <div class="btn-row">
      <button class="btn btn-gold btn-lg" onclick="doGenerate()">⚡ Generate Teams</button>
      <button class="btn btn-ghost" onclick="resetAll()">↺ Reset</button>
    </div>
  </div>

</div><!-- /wrap -->

<!-- Content section -->
<div class="content-section z1">
  <h2>How FantasyXI Works</h2>
  <p>FantasyXI uses a smart distribution engine to generate up to 20 unique fantasy cricket teams for any ICC T20 World Cup 2026 Super 8s match. Every team is built exclusively from the confirmed Playing XI of each side — bench players are never included.</p>

  <h3>Three Risk Modes</h3>
  <p>Choose <strong>Safe</strong> for low-risk captains and stable picks, <strong>Balanced</strong> for mixed-risk smart rotation, or <strong>Risky</strong> for high-differential maximum-ceiling teams. All modes strictly use the top 11 confirmed players.</p>

  <h3>Advanced Distribution Rules</h3>
  <p>The engine enforces role constraints (1–4 WK, 3–6 Batsmen, 1–4 All-rounders, 3–6 Bowlers), avoids duplicate team combinations, rotates C/VC pairs intelligently, limits player exposure, and respects lock/exclude player controls. Advanced options like differential inclusion and balanced distribution give you full strategic control.</p>

  <h2 style="margin-top:30px;">Frequently Asked Questions</h2>

  <div class="faq-item">
    <div class="faq-q" onclick="toggleFaq(this)">Is FantasyXI free to use? <span class="arrow">▼</span></div>
    <div class="faq-a">Yes. The first 3 generated teams are always completely free. You can unlock the remaining teams by watching a short 5-second simulated ad — no real payment required.</div>
  </div>
  <div class="faq-item">
    <div class="faq-q" onclick="toggleFaq(this)">Which players are included? <span class="arrow">▼</span></div>
    <div class="faq-a">All teams are built exclusively from the confirmed Playing XI (players 1–11) of each team. Bench players are never used in any mode.</div>
  </div>
  <div class="faq-item">
    <div class="faq-q" onclick="toggleFaq(this)">What is the difference between Safe, Balanced, and Risky modes? <span class="arrow">▼</span></div>
    <div class="faq-a">Safe weights low-risk players and always selects captains from low-risk players — ideal for small contests. Balanced mixes low and medium risk. Risky weights high-risk differentials heavily and is best for mega contests where you need to stand out.</div>
  </div>
  <div class="faq-item">
    <div class="faq-q" onclick="toggleFaq(this)">Can I export my teams? <span class="arrow">▼</span></div>
    <div class="faq-a">Yes. After unlocking all teams, you can export all of them as a clean, formatted PDF. Each team can also be individually copied to your clipboard with one click.</div>
  </div>
  <div class="faq-item">
    <div class="faq-q" onclick="toggleFaq(this)">Are these teams guaranteed to win? <span class="arrow">▼</span></div>
    <div class="faq-a">No. FantasyXI is an informational and entertainment tool. Team performance depends on real match outcomes. Always play responsibly. FantasyXI does not guarantee any winnings.</div>
  </div>
  <div class="faq-item">
    <div class="faq-q" onclick="toggleFaq(this)">Is this site affiliated with Dream11, ICC, or BCCI? <span class="arrow">▼</span></div>
    <div class="faq-a">No. FantasyXI is an independent tool. It is not affiliated with Dream11, ICC, BCCI, or any official cricket or fantasy sports organisation.</div>
  </div>
</div><!-- /content-section -->

""" + _FOOTER + _AD_MODAL + """

<script>
var selT1=null, selT2=null, selMID=null, selMode=null;

function showTab(id, el) {
  document.getElementById('tab-up').style.display = id==='up' ? '' : 'none';
  document.getElementById('tab-man').style.display = id==='man' ? '' : 'none';
  document.querySelectorAll('.tab-btn').forEach(function(b){ b.classList.remove('active'); });
  el.classList.add('active');
}

/* Part 4: auto-scroll after match select */
function selectMatch(id, t1, t2, date, venue, el) {
  selMID=id; selT1=t1; selT2=t2;
  document.querySelectorAll('.match-card').forEach(function(c){ c.classList.remove('selected'); });
  el.classList.add('selected');
  var info = document.getElementById('selInfo');
  info.style.display = 'block';
  info.innerHTML = '✅ <strong>' + t1 + ' vs ' + t2 + '</strong> · ' + date + ' · 📍 ' + venue;
  setTimeout(function(){ scrollTo('section-mode'); }, 220);
}

function setManual() {
  var t1 = document.getElementById('mt1').value;
  var t2 = document.getElementById('mt2').value;
  if (t1===t2) { showToast('Please select two different teams!', '#f04f4f'); return; }
  selT1=t1; selT2=t2; selMID='manual';
  showToast('✅ Teams confirmed! Choose a mode below.', '#f0b429');
  setTimeout(function(){ scrollTo('section-mode'); }, 220);
}

/* Part 4: auto-scroll after mode select */
function selectMode(m, el) {
  selMode = m;
  document.querySelectorAll('.mode-card').forEach(function(c){ c.classList.remove('active'); });
  el.classList.add('active');
  setTimeout(function(){ scrollTo('section-criteria'); }, 220);
}

function parseIds(str) {
  if (!str || !str.trim()) return [];
  return str.split(',').map(function(s){ return s.trim(); }).filter(Boolean);
}

function doGenerate() {
  if (!selT1 || !selT2) { showToast('Please select a match first!', '#f04f4f'); return; }
  if (!selMode)         { showToast('Please choose a generation mode!', '#f04f4f'); return; }

  var cr = {};
  ['c1','c6','c7','c8','c11','c12','c13','c14','c15'].forEach(function(k) {
    var el = document.getElementById(k);
    cr[k] = el ? el.checked : true;
  });

  var adv = {
    unique_cap:   document.getElementById('unique_cap') ? document.getElementById('unique_cap').checked : false,
    unique_vc:    document.getElementById('unique_vc') ? document.getElementById('unique_vc').checked : false,
    differential: document.getElementById('differential') ? document.getElementById('differential').checked : false,
    balanced_dist: document.getElementById('balanced_dist') ? document.getElementById('balanced_dist').checked : false,
    exposure_pct: parseInt(document.getElementById('exposure') ? document.getElementById('exposure').value : 75) || 75,
    max_from_one: parseInt(document.getElementById('max_from_one') ? document.getElementById('max_from_one').value : 7) || 7,
    locked:       parseIds(document.getElementById('locked_players') ? document.getElementById('locked_players').value : ''),
    excluded:     parseIds(document.getElementById('excluded_players') ? document.getElementById('excluded_players').value : '')
  };

  var payload = {
    team1: selT1, team2: selT2, match_id: selMID, mode: selMode,
    nt: Math.min(parseInt(document.getElementById('nt').value) || 20, 20),
    cr: cr, adv: adv
  };

  var form = document.createElement('form');
  form.method = 'POST'; form.action = '/generate';
  var inp = document.createElement('input');
  inp.type = 'hidden'; inp.name = 'payload'; inp.value = JSON.stringify(payload);
  form.appendChild(inp); document.body.appendChild(form); form.submit();
}

function resetAll() {
  selT1=selT2=selMID=selMode=null;
  document.querySelectorAll('.match-card').forEach(function(c){ c.classList.remove('selected'); });
  document.querySelectorAll('.mode-card').forEach(function(c){ c.classList.remove('active'); });
  document.getElementById('selInfo').style.display='none';
}
</script>
""" + _SHARED_JS + """
</body>
</html>
"""

# ─── RESULTS PAGE ─────────────────────────────────────────────────────────────
# Part 1: Correct order: Free teams → Unlock banner → Locked teams (all in grid)

RESULTS_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<title>FantasyXI — {{team1}} vs {{team2}} · Generated Teams</title>
<meta name="description" content="20 unique fantasy cricket teams for {{team1}} vs {{team2}}. ICC T20 World Cup 2026 Super 8s.">
<meta name="robots" content="noindex, nofollow">
""" + _CSS + """
</head>
<body>

<header>
  <div class="logo-wrap">
    <div class="logo">⚡ FantasyXI</div>
    <span class="logo-badge">Super 8s · T20 WC 2026</span>
  </div>
  <nav class="hdr-nav">
    <a href="/">← Home</a>
    <a href="#" onclick="window.print();return false;">🖨 Print</a>
    <a href="/export_pdf" id="pdfBtn" {% if not unlocked %}style="display:none"{% endif %} class="cta">📄 PDF</a>
  </nav>
</header>

<div class="wrap z1">

  <!-- Match strip -->
  <div class="match-strip">
    <div>
      <div class="strip-vs">{{team1}}<em>VS</em>{{team2}}</div>
      {% if venue %}<div class="strip-venue">📍 {{venue}}</div>{% endif %}
    </div>
    <div class="strip-right">
      <span class="pill pill-{{mode}}">{{mode|upper}}</span>
      <span class="pill pill-neutral">{{teams|length}} Teams</span>
    </div>
  </div>

  <!-- Stats -->
  <div class="stats-bar">
    <div class="stat-chip"><strong>{{teams|length}}</strong><span>Total</span></div>
    <div class="stat-chip"><strong>3</strong><span>Free</span></div>
    <div class="stat-chip"><strong>{{teams|length - 3}}</strong><span>Locked</span></div>
    <div class="stat-chip"><strong>{{unique_caps}}</strong><span>Captains</span></div>
    <div class="stat-chip"><strong>{{cv_combos}}</strong><span>C/VC Combos</span></div>
    <div class="stat-chip"><strong>XI Only</strong><span>Pool</span></div>
  </div>

  <div class="res-topbar">
    <div class="sh" style="margin-bottom:0;">Generated Teams</div>
    {% if unlocked %}
    <a href="/export_pdf" class="btn btn-grn" style="font-size:.85rem;padding:9px 17px;">📄 Export PDF</a>
    {% endif %}
  </div>

  <!-- ═══════════════════════════════════════════════════
       PART 1 — CORRECT LAYOUT:
       1. Free teams (1-3)
       2. Unlock banner (full-width)
       3. Locked teams (4-N)
       All inside one CSS grid for correct placement.
       ═══════════════════════════════════════════════════ -->

  <div class="team-grid" id="mainGrid">

    <!-- FREE TEAMS (1-3) -->
    {% for t in teams[:3] %}
    <div class="team-card fade-up" style="animation-delay:{{loop.index0 * 0.04}}s;">
      <div class="team-hdr">
        <div class="team-num">Team {{loop.index}}</div>
        <span class="badge badge-free">FREE ✓</span>
      </div>
      <div class="cv-row">
        <div class="cv-pill cv-c">
          <span class="cv-lbl">Captain 2×</span>
          <span class="cv-nm">{{t.captain}}</span>
        </div>
        <div class="cv-pill cv-vc">
          <span class="cv-lbl">Vice Captain 1.5×</span>
          <span class="cv-nm">{{t.vice_captain}}</span>
        </div>
      </div>
      <ul class="plist">
      {% for p in t.players %}
        <li class="pitem">
          {% if p.role=='Batsman' %}<div class="rdot d-bat"></div>
          {% elif p.role=='Bowler' %}<div class="rdot d-bowl"></div>
          {% elif p.role=='All-rounder' %}<div class="rdot d-ar"></div>
          {% else %}<div class="rdot d-wk"></div>{% endif %}
          <span class="pname">{{p.name}}
            {% if p.name==t.captain %}<span class="ct">(C)</span>{% endif %}
            {% if p.name==t.vice_captain %}<span class="vct">(VC)</span>{% endif %}
          </span>
          <span class="rtag r{{p.risk_level[0]}}">{{p.risk_level}}</span>
        </li>
      {% endfor %}
      </ul>
      <div class="card-foot">
        <div class="foot-info">{{t.from_t1}} {{team1}} · {{t.from_t2}} {{team2}}</div>
        <button class="copy-btn" onclick="copyTeam({{loop.index0}})">📋 Copy</button>
      </div>
    </div>
    {% endfor %}

    <!-- ─── UNLOCK BANNER (PART 1 — placed inline in grid after team 3) ─── -->
    {% if not unlocked %}
    <div class="unlock-banner fade-up" id="unlockBanner" style="animation-delay:.15s;">
      <h3>🎬 Unlock All {{teams|length - 3}} Remaining Teams</h3>
      <p>Watch one short 5-second simulated ad — no real ad SDK required.</p>
      <button class="btn btn-ora btn-lg" onclick="openAd()">▶ Watch 1 Ad to Unlock All Teams</button>
    </div>
    {% endif %}

    <!-- LOCKED TEAMS (4-N) -->
    {% for t in teams[3:] %}
    <div class="team-card fade-up" style="animation-delay:{{(loop.index + 3) * 0.03}}s;">
      <div class="team-hdr">
        <div class="team-num">Team {{loop.index + 3}}</div>
        <span class="badge badge-lock">🔒 LOCKED</span>
      </div>
      <div class="cv-row">
        <div class="cv-pill cv-c">
          <span class="cv-lbl">Captain 2×</span>
          <span class="cv-nm">{{t.captain}}</span>
        </div>
        <div class="cv-pill cv-vc">
          <span class="cv-lbl">Vice Captain 1.5×</span>
          <span class="cv-nm">{{t.vice_captain}}</span>
        </div>
      </div>
      <ul class="plist">
      {% for p in t.players %}
        <li class="pitem">
          {% if p.role=='Batsman' %}<div class="rdot d-bat"></div>
          {% elif p.role=='Bowler' %}<div class="rdot d-bowl"></div>
          {% elif p.role=='All-rounder' %}<div class="rdot d-ar"></div>
          {% else %}<div class="rdot d-wk"></div>{% endif %}
          <span class="pname">{{p.name}}
            {% if p.name==t.captain %}<span class="ct">(C)</span>{% endif %}
            {% if p.name==t.vice_captain %}<span class="vct">(VC)</span>{% endif %}
          </span>
          <span class="rtag r{{p.risk_level[0]}}">{{p.risk_level}}</span>
        </li>
      {% endfor %}
      </ul>
      <div class="card-foot">
        <div class="foot-info">{{t.from_t1}} {{team1}} · {{t.from_t2}} {{team2}}</div>
        {% if not unlocked %}
          <button class="copy-btn" onclick="copyTeam({{loop.index + 2}})" disabled>📋 Copy</button>
        {% else %}
          <button class="copy-btn" onclick="copyTeam({{loop.index + 2}})">📋 Copy</button>
        {% endif %}
      </div>

      {% if not unlocked %}
      <div class="lock-ov">
        <div class="lock-ico">🔒</div>
        <div class="lock-lbl">LOCKED</div>
        <div class="lock-sub">Watch ad to unlock</div>
      </div>
      {% endif %}
    </div>
    {% endfor %}

  </div><!-- /team-grid -->

  {% if unlocked %}
  <div style="text-align:center;margin:32px 0;">
    <a href="/export_pdf" class="btn btn-grn btn-lg">📄 Export All {{teams|length}} Teams as PDF</a>
  </div>
  {% endif %}

</div><!-- /wrap -->

""" + _FOOTER + _AD_MODAL + _SHARED_JS + """
</body>
</html>
"""

# ─── LEGAL PAGES ──────────────────────────────────────────────────────────────

def legal_wrap(title, body):
    return """<!DOCTYPE html>
<html lang="en">
<head>
<title>""" + title + """ — FantasyXI</title>
<meta name="robots" content="index, follow">
""" + _CSS + """
</head>
<body>
<header>
  <div class="logo-wrap">
    <div class="logo">⚡ FantasyXI</div>
    <span class="logo-badge">T20 WC 2026</span>
  </div>
  <nav class="hdr-nav">
    <a href="/">← Home</a><a href="/about">About</a><a href="/contact">Contact</a>
  </nav>
</header>
<div class="legal-wrap z1">""" + body + """</div>
""" + _FOOTER + """
<div class="toast" id="toast"></div>
</body>
</html>"""

PRIVACY_BODY = """
<h1>Privacy Policy</h1>
<p class="last-updated">Last updated: January 2026</p>
<h2>Introduction</h2>
<p>FantasyXI ("we", "our", "us") is committed to protecting your personal information and your right to privacy. This Privacy Policy explains how we collect, use, disclose, and safeguard your information when you visit our website.</p>
<h2>Information We Collect</h2>
<p>We may collect information about you in a variety of ways. The information we may collect includes:</p>
<ul>
  <li><strong>Log and Usage Data:</strong> Server logs, IP addresses, browser type, pages visited, and time of visit.</li>
  <li><strong>Cookies and Tracking Technologies:</strong> We use cookies and similar tracking technologies to improve your experience. You can control cookies through your browser settings.</li>
  <li><strong>Contact Form Data:</strong> If you contact us via our contact form, we collect your name, email address, and message content.</li>
</ul>
<h2>How We Use Your Information</h2>
<p>We use the information we collect to operate and maintain our website, improve and expand our services, understand and analyse usage patterns, and respond to your enquiries.</p>
<h2>Google AdSense and Third-Party Advertising</h2>
<p>FantasyXI uses Google AdSense to display advertisements. Google AdSense uses cookies to serve ads based on your prior visits to this website or other websites. You may opt out of personalised advertising by visiting <a href="https://www.google.com/settings/ads" target="_blank" rel="noopener">Google Ad Settings</a>.</p>
<p>Third-party vendors, including Google, use cookies to serve ads based on your prior visits to our website. Google's use of the DoubleClick cookie enables it and its partners to serve ads based on your visits to this and other sites.</p>
<h2>Cookies Policy</h2>
<p>Cookies are small text files stored on your device. We use session cookies (to remember your generated teams within a session), analytics cookies (to understand usage), and advertising cookies (Google AdSense for relevant advertising).</p>
<p>You can instruct your browser to refuse all cookies or indicate when a cookie is being sent. However, some portions of our site may not function properly without cookies.</p>
<h2>Third-Party Links</h2>
<p>Our website may contain links to third-party sites. We have no control over and assume no responsibility for the content, privacy policies, or practices of any third-party sites.</p>
<h2>Children's Privacy</h2>
<p>FantasyXI is intended for users aged 18 and over. We do not knowingly collect personally identifiable information from anyone under the age of 18.</p>
<h2>Data Security</h2>
<p>We use appropriate technical and organisational measures to protect your personal information. However, no method of transmission over the Internet is 100% secure.</p>
<h2>Changes to This Policy</h2>
<p>We may update our Privacy Policy from time to time. We will notify you by updating the "Last updated" date at the top of this page.</p>
<h2>Contact Us</h2>
<p>If you have questions, contact us at: <a href="mailto:contact@fantasyxi.in">contact@fantasyxi.in</a> or via our <a href="/contact">Contact page</a>.</p>
"""

TERMS_BODY = """
<h1>Terms &amp; Conditions</h1>
<p class="last-updated">Last updated: January 2026</p>
<h2>Acceptance of Terms</h2>
<p>By accessing and using FantasyXI ("the website"), you accept and agree to be bound by the terms and provision of this agreement. If you do not agree to these terms, please do not use our website.</p>
<h2>Use of Service</h2>
<p>FantasyXI provides a fantasy cricket team generator tool for informational and entertainment purposes only. You agree to use this service only for lawful purposes and in accordance with these Terms.</p>
<p>You agree not to use automated means to scrape content, interfere with or disrupt the integrity of the website, attempt to gain unauthorised access to any portion of the website, or use the service in any way that violates applicable laws or regulations.</p>
<h2>Age Restriction</h2>
<p>This website is intended for users who are 18 years of age or older. By using this site, you represent and warrant that you are at least 18 years old.</p>
<h2>No Guarantee of Winnings</h2>
<p>FantasyXI is a team suggestion and educational tool. We do not guarantee any winnings in fantasy sports platforms. Fantasy sports involve risk and outcomes depend on real-world sporting events outside our control.</p>
<h2>Intellectual Property</h2>
<p>The content, design, and functionality of FantasyXI are the intellectual property of FantasyXI. Player names and match data used for informational purposes are property of their respective rights holders. FantasyXI is not affiliated with Dream11, ICC, BCCI, or any other official body.</p>
<h2>Disclaimer of Warranties</h2>
<p>The service is provided on an "AS IS" and "AS AVAILABLE" basis without any warranties of any kind.</p>
<h2>Limitation of Liability</h2>
<p>In no event shall FantasyXI, its directors, employees, or agents be liable for any indirect, incidental, special, consequential, or punitive damages arising out of your use of the service.</p>
<h2>Governing Law</h2>
<p>These Terms shall be governed and construed in accordance with the laws of India, without regard to its conflict of law provisions.</p>
<h2>Contact</h2>
<p>For any questions regarding these Terms, please contact us at <a href="mailto:contact@fantasyxi.in">contact@fantasyxi.in</a>.</p>
"""

ABOUT_BODY = """
<h1>About FantasyXI</h1>
<p class="last-updated">Your trusted ICC T20 World Cup 2026 fantasy team generator</p>

<div class="about-grid">
  <div class="about-card"><div class="about-icon">⚡</div><h3>Smart Engine</h3><p>Advanced distribution algorithm ensures 20 unique, optimised teams with no duplicates.</p></div>
  <div class="about-card"><div class="about-icon">🏆</div><h3>Super 8s Coverage</h3><p>All Super 8 stage matches of ICC T20 World Cup 2026, with updated confirmed squads.</p></div>
  <div class="about-card"><div class="about-icon">📊</div><h3>Data-Driven</h3><p>Risk-level weighting, role constraints, C/VC rotation, exposure limits — all automated.</p></div>
  <div class="about-card"><div class="about-icon">🔒</div><h3>Privacy First</h3><p>No login required. No personal data stored beyond session. Transparent and clean.</p></div>
</div>

<h2>Our Mission</h2>
<p>FantasyXI was created to help fantasy cricket enthusiasts efficiently generate diversified fantasy teams for ICC T20 World Cup 2026 Super 8s matches. Instead of spending hours manually creating teams, our smart engine does it in seconds — applying proven distribution rules used by top fantasy players.</p>

<h2>What Makes FantasyXI Different?</h2>
<p>Unlike basic random generators, FantasyXI's engine enforces role constraints ensuring every team has the correct WK/BAT/AR/BOWL balance, produces no duplicate teams, distributes C/VC intelligently across different players and roles, offers risk mode weighting so Safe, Balanced, and Risky modes produce genuinely different output, and only ever selects from confirmed playing XI players.</p>

<h2>Disclaimer</h2>
<p>FantasyXI is an independent, informational tool. It is not affiliated with Dream11, MyTeam11, ICC, BCCI, or any official cricket or fantasy sports organisation. All player names and match data are used for informational and educational purposes only. Fantasy sports involve risk — please play responsibly and within your means.</p>

<p>For questions or feedback, please visit our <a href="/contact">Contact page</a>.</p>
"""

HOW_BODY = """
<h1>How FantasyXI Works</h1>
<p class="last-updated">A step-by-step guide to generating your optimised fantasy teams</p>

<h2>Step 1 — Select a Match</h2>
<p>From the home page, choose any upcoming ICC T20 World Cup 2026 Super 8s match from the match cards. Each card shows the two teams, date, time, and venue. Alternatively, use Manual Selection to pick any two teams from the full squad database.</p>

<h2>Step 2 — Choose a Generation Mode</h2>
<p>Select one of three modes based on your contest strategy. Safe mode weights low-risk players heavily and always picks captains from low-risk players only — ideal for small contests or head-to-head matchups where consistency matters most. Balanced mode mixes low and medium risk, good for mid-size contests. Risky mode weights high-risk differential players heavily, best for large tournaments where you need to stand out from the crowd.</p>

<h2>Step 3 — Configure Advanced Criteria</h2>
<p>Fine-tune the distribution engine with advanced options. Set the number of teams, control player exposure limits (max % of teams a player can appear in), set max players from one team, enable unique C/VC per team rules, lock specific players to appear in every team, exclude specific players entirely, and enable differential inclusion for the last 10 teams.</p>

<h2>Step 4 — Generate &amp; Review</h2>
<p>Click "Generate Teams." The engine produces up to 20 unique teams instantly. The first 3 are immediately visible and free. The remaining teams can be unlocked by watching a short 5-second simulated ad — no payment required.</p>

<h2>Step 5 — Copy or Export</h2>
<p>Each team card has a one-click Copy button to copy the team (C, VC, all 11 players) to your clipboard. After unlocking, you can also export all teams as a formatted PDF.</p>

<h2>Role Constraints Explained</h2>
<p>Every generated team satisfies these fantasy platform role rules: 1–4 Wicketkeeper-Batsmen, 3–6 Batsmen, 1–4 All-rounders, 3–6 Bowlers, and a maximum of 7 players from either team (configurable via Advanced Criteria).</p>

<h2>Understanding Risk Levels</h2>
<p>Each player in the squad database has an assigned risk level. Low Risk players are consistent, established performers likely to score in most conditions. Medium Risk players have good potential but some variance in output. High Risk players are differentials — high ceiling but less consistent, great for large contests where you need separation from the field.</p>
"""

DISCLAIMER_BODY = """
<h1>Disclaimer</h1>
<p class="last-updated">Last updated: January 2026</p>
<h2>General Disclaimer</h2>
<p>The information provided by FantasyXI on this website is for general informational and entertainment purposes only. All information is provided in good faith; however, we make no representation or warranty of any kind, express or implied, regarding the accuracy, adequacy, validity, reliability, availability, or completeness of any information on the site.</p>
<h2>Fantasy Sports Disclaimer</h2>
<p>Fantasy sports involve an element of financial risk and may be addictive. Please play responsibly and at your own risk. FantasyXI does not guarantee any winnings. Outcomes in fantasy platforms depend entirely on real sporting events which we cannot predict or control.</p>
<p>Check the legality of fantasy sports in your state/country before participating in paid contests. Fantasy sports for cash prizes may be restricted or prohibited in some jurisdictions.</p>
<h2>Affiliation Disclaimer</h2>
<p>FantasyXI is an independent website and is not affiliated with, authorised by, maintained, sponsored, or endorsed by Dream11, MyTeam11, ICC, BCCI, or any other fantasy platform or cricket governing body.</p>
<h2>External Links</h2>
<p>FantasyXI may contain links to external websites. We have no control over the content of those sites and accept no responsibility for them or for any loss or damage that may arise from your use of them.</p>
<h2>18+ Notice</h2>
<p>This website is intended for users aged 18 and above. Minors should not participate in paid fantasy sports contests.</p>
<h2>Contact</h2>
<p>If you have any questions about this Disclaimer, contact us at <a href="mailto:contact@fantasyxi.in">contact@fantasyxi.in</a>.</p>
"""

CONTACT_BODY = """
<h1>Contact Us</h1>
<p class="last-updated">We'd love to hear from you — feedback, bug reports, or partnerships.</p>

<h2>Get in Touch</h2>
<p>📧 Email: <a href="mailto:contact@fantasyxi.in">contact@fantasyxi.in</a></p>
<p>We aim to respond within 48 hours on working days.</p>

<h2>Send a Message</h2>
<form class="contact-form" onsubmit="submitForm(event)">
  <div class="form-group">
    <label for="cf-name">Your Name *</label>
    <input type="text" id="cf-name" placeholder="Rahul Sharma" required>
  </div>
  <div class="form-group">
    <label for="cf-email">Email Address *</label>
    <input type="email" id="cf-email" placeholder="rahul@example.com" required>
  </div>
  <div class="form-group">
    <label for="cf-subject">Subject</label>
    <select id="cf-subject">
      <option>General Enquiry</option>
      <option>Bug Report</option>
      <option>Feature Request</option>
      <option>Partnership / Advertising</option>
      <option>Other</option>
    </select>
  </div>
  <div class="form-group">
    <label for="cf-msg">Message *</label>
    <textarea id="cf-msg" placeholder="Your message here..." required></textarea>
  </div>
  <button type="submit" class="btn btn-gold">Send Message →</button>
</form>
<div class="form-msg" id="formMsg">✅ Thank you! Your message has been received. We'll get back to you within 48 hours.</div>

<script>
function submitForm(e) {
  e.preventDefault();
  var name=document.getElementById('cf-name').value;
  var email=document.getElementById('cf-email').value;
  var msg=document.getElementById('cf-msg').value;
  if (!name||!email||!msg) return;
  document.querySelector('.contact-form').style.display='none';
  document.getElementById('formMsg').style.display='block';
}
</script>
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
    nt       = min(int(p.get("nt", 20)), 20)
    cr       = p.get("cr", {})
    adv      = p.get("adv", {})

    tbn = teams_by_name()
    if team1 not in tbn: return f"Team not found: {team1!r}", 400
    if team2 not in tbn: return f"Team not found: {team2!r}", 400

    teams, ucaps, cvcombos = gen_teams(team1, team2, mode, cr, nt, adv)

    venue = ""
    if match_id != "manual":
        for m in load_matches()["matches"]:
            if m["match_id"] == match_id:
                venue = m.get("venue", ""); break

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

    gen = session.get("gen", {})
    teams = gen.get("teams", [])
    if not teams: return "No teams in session.", 400

    team1    = gen.get("team1", "T1")
    team2    = gen.get("team2", "T2")
    mode     = gen.get("mode", "balanced").upper()
    venue    = gen.get("venue", "")
    unlocked = session.get("unlocked", False)

    GOLD = colors.HexColor("#f0b429")
    DARK = colors.HexColor("#141926")
    DARK2 = colors.HexColor("#0c1220")
    MUTED = colors.HexColor("#64748b")
    WHT = colors.white

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4,
                            leftMargin=1.4*cm, rightMargin=1.4*cm,
                            topMargin=1.8*cm, bottomMargin=1.8*cm)

    def S(n, **kw): return ParagraphStyle(n, **kw)
    sT  = S("t",  fontSize=20, textColor=GOLD, fontName="Helvetica-Bold", alignment=1, spaceAfter=4)
    sS  = S("s",  fontSize=9,  textColor=MUTED, alignment=1, spaceAfter=5)
    sTH = S("th", fontSize=13, textColor=GOLD, fontName="Helvetica-Bold", spaceAfter=5)
    sCV = S("cv", fontSize=9,  textColor=WHT, spaceAfter=4)
    sFT = S("ft", fontSize=7.5, textColor=MUTED, spaceBefore=3)

    story = []
    story.append(Paragraph("FantasyXI", sT))
    story.append(Paragraph("ICC Men's T20 World Cup 2026 - Super 8s", sS))
    story.append(Paragraph(f"{team1} VS {team2}  |  {mode} Mode  |  Playing XI Only", sS))
    if venue: story.append(Paragraph(f"Venue: {venue}", sS))
    story.append(Spacer(1, .2*cm))
    story.append(HRFlowable(width="100%", thickness=1, color=GOLD))
    story.append(Spacer(1, .4*cm))

    max_idx = len(teams) if unlocked else 3
    for idx, t in enumerate(teams[:max_idx]):
        story.append(Paragraph(f"Team {idx+1}", sTH))
        story.append(Paragraph(
            f"<b><font color='#f0b429'>Captain (2x):</font></b> {t['captain']}     "
            f"<b><font color='#4fa3e0'>VC (1.5x):</font></b> {t['vice_captain']}", sCV))
        rows = [["#", "Player", "Role", "Risk"]]
        for pi, p in enumerate(t["players"]):
            tag = " (C)" if p["name"] == t["captain"] else (" (VC)" if p["name"] == t["vice_captain"] else "")
            rows.append([str(pi+1), p["name"]+tag, p["role"], p["risk_level"]])
        tbl = Table(rows, colWidths=[.7*cm, 7*cm, 4.5*cm, 2.5*cm])
        tbl.setStyle(TableStyle([
            ("BACKGROUND", (0,0), (-1,0), DARK2), ("TEXTCOLOR", (0,0), (-1,0), GOLD),
            ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold"), ("FONTSIZE", (0,0), (-1,-1), 8.5),
            ("TEXTCOLOR", (0,1), (-1,-1), WHT),
            ("ROWBACKGROUNDS", (0,1), (-1,-1), [DARK, colors.HexColor("#18202e")]),
            ("GRID", (0,0), (-1,-1), .3, colors.HexColor("#2a2b45")),
            ("ALIGN", (0,0), (0,-1), "CENTER"),
            ("TOPPADDING", (0,0), (-1,-1), 5), ("BOTTOMPADDING", (0,0), (-1,-1), 5),
            ("LEFTPADDING", (0,0), (-1,-1), 6),
        ]))
        story.append(tbl)
        story.append(Paragraph(f"{t['from_t1']} from {team1} | {t['from_t2']} from {team2}", sFT))
        story.append(Spacer(1, .5*cm))
        if (idx+1) % 2 == 0 and idx < max_idx-1:
            story.append(PageBreak())

    doc.build(story)
    buf.seek(0)
    return send_file(buf, mimetype="application/pdf", as_attachment=True,
                     download_name=f"FantasyXI_{team1}_vs_{team2}.pdf")


# ─── Legal & Info pages ───────────────────────────────────────────────────────

@app.route("/privacy")
def privacy():
    return legal_wrap("Privacy Policy", PRIVACY_BODY)

@app.route("/terms")
def terms():
    return legal_wrap("Terms & Conditions", TERMS_BODY)

@app.route("/about")
def about():
    return legal_wrap("About Us", ABOUT_BODY)

@app.route("/how-it-works")
def how_it_works():
    return legal_wrap("How It Works", HOW_BODY)

@app.route("/disclaimer")
def disclaimer():
    return legal_wrap("Disclaimer", DISCLAIMER_BODY)

@app.route("/contact")
def contact():
    return legal_wrap("Contact Us", CONTACT_BODY)


# ─── SEO files ────────────────────────────────────────────────────────────────

@app.route("/robots.txt")
def robots():
    txt = """User-agent: *
Allow: /
Allow: /about
Allow: /how-it-works
Allow: /privacy
Allow: /terms
Allow: /disclaimer
Allow: /contact
Disallow: /generate
Disallow: /export_pdf
Disallow: /unlock
Sitemap: https://fantasyxi.in/sitemap.xml
"""
    return Response(txt, mimetype="text/plain")


@app.route("/sitemap.xml")
def sitemap():
    today = datetime.date.today().isoformat()
    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://fantasyxi.in/</loc><lastmod>{today}</lastmod><changefreq>daily</changefreq><priority>1.0</priority></url>
  <url><loc>https://fantasyxi.in/about</loc><lastmod>{today}</lastmod><changefreq>monthly</changefreq><priority>0.8</priority></url>
  <url><loc>https://fantasyxi.in/how-it-works</loc><lastmod>{today}</lastmod><changefreq>monthly</changefreq><priority>0.8</priority></url>
  <url><loc>https://fantasyxi.in/privacy</loc><lastmod>{today}</lastmod><changefreq>yearly</changefreq><priority>0.5</priority></url>
  <url><loc>https://fantasyxi.in/terms</loc><lastmod>{today}</lastmod><changefreq>yearly</changefreq><priority>0.5</priority></url>
  <url><loc>https://fantasyxi.in/disclaimer</loc><lastmod>{today}</lastmod><changefreq>yearly</changefreq><priority>0.5</priority></url>
  <url><loc>https://fantasyxi.in/contact</loc><lastmod>{today}</lastmod><changefreq>monthly</changefreq><priority>0.6</priority></url>
</urlset>"""
    return Response(xml, mimetype="application/xml")


# ─── Run ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app.run(debug=True, port=5000)
