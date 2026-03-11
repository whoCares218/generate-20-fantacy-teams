# =============================================================================
# AI Fantasy Team Generator — Flask app | v4.0 — AdSense Compliant
# Supports IPL, T20 World Cup, ICC tournaments, and all major cricket leagues
# =============================================================================

import json, random, hashlib, io, datetime, smtplib, threading
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from flask import (Flask, render_template_string, request,
                   jsonify, send_file, session, Response)
from collections import defaultdict

app = Flask(__name__)
app.secret_key = "fantasyxi_t20wc_2026_sk_v3"

# ─── Email Configuration ──────────────────────────────────────────────────────
SMTP_HOST     = "smtp.gmail.com"
SMTP_PORT     = 587
SMTP_USER     = "tehm8111@gmail.com"
SMTP_PASSWORD = "idkl poic jbvh ysou"
EMAIL_TO      = "tehm8111@gmail.com"

def _smtp_send(name, email, subject, message):
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"]  = f"[FantasyXI Contact] {subject} — from {name}"
        msg["From"]     = SMTP_USER
        msg["To"]       = EMAIL_TO
        msg["Reply-To"] = email
        html_body = f"""<div style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;">
          <h2>New Contact: {name}</h2><p>Email: {email}</p><p>Subject: {subject}</p>
          <p>{message}</p></div>"""
        text_body = f"Name: {name}\nEmail: {email}\nSubject: {subject}\n\n{message}"
        msg.attach(MIMEText(text_body, "plain"))
        msg.attach(MIMEText(html_body, "html"))
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=10) as server:
            server.ehlo(); server.starttls(); server.ehlo()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.sendmail(SMTP_USER, EMAIL_TO, msg.as_string())
    except Exception as e:
        print(f"[Email ERROR] {e}")

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
    locked_ids   = set(adv.get("locked", []))
    excluded_ids = set(adv.get("excluded", []))
    max_from_one = int(adv.get("max_from_one", 7))
    exposure_pct = float(adv.get("exposure_pct", 75)) / 100.0
    risk_intensity = float(adv.get("risk_intensity", 1.0))
    rand_strength  = float(adv.get("rand_strength", 0.5))
    min_diff       = int(adv.get("min_diff", 0))
    safe_core      = adv.get("safe_core", False)
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
            adj_weights = [w * (1 + rand_strength * (random.random() - 0.5)) for w in (free_weights or [1]*len(free_pool))]
            adj_weights = [max(w, 0.01) for w in adj_weights]
            tries = random.choices(free_pool, weights=adj_weights, k=min(len(free_pool), need * 6))
            for p in tries:
                if p["id"] not in seen:
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
            w1 = [risk_weight(p, mode) * risk_intensity for p in pool1]
            w2 = [risk_weight(p, mode) * risk_intensity for p in pool2]
            if adv.get("differential", False) and idx >= 10:
                w1 = [w * max(0.5, 1 - appear[p["id"]] / max(nt, 1)) for p, w in zip(pool1, w1)]
                w2 = [w * max(0.5, 1 - appear[p["id"]] / max(nt, 1)) for p, w in zip(pool2, w2)]
            if min_diff > 0 and idx >= 5:
                low_appear1 = sorted(pool1, key=lambda p: appear[p["id"]])[:min_diff]
                low_appear2 = sorted(pool2, key=lambda p: appear[p["id"]])[:min_diff]
                for p in low_appear1 + low_appear2: locked_ids.add(p["id"])
            sel1 = pick_unique(pool1, w1, n1, locked_ids)
            sel2 = pick_unique(pool2, w2, n2, locked_ids)
            if min_diff > 0 and idx >= 5:
                for p in low_appear1 + low_appear2: locked_ids.discard(p["id"])
                for lid in adv.get("locked", []): locked_ids.add(lid)
            if len(sel1) != n1 or len(sel2) != n2: continue
            players = sel1 + sel2
            if cr.get("c14", True) and not roles_ok(players): continue
            max_one = max_from_one if adv.get("max_from_one") else 7
            if cr.get("c13", True) and (len(sel1) > max_one or len(sel2) > max_one): continue
            h = hash_team([p["id"] for p in players])
            if cr.get("c12", True) and h in th_set: continue
            cp = cap_pool(players)
            def cw(p):
                b = risk_weight(p, mode) * risk_intensity
                b /= (1 + cap_cnt[p["id"]] * 0.5)
                return max(b, 0.05)
            cws = [cw(p) for p in cp]
            if cr.get("c11", True) and len(last_cap) >= 3 and len(set(last_cap[-3:])) == 1:
                forb = last_cap[-3]
                alt = [(p, w) for p, w in zip(cp, cws) if p["id"] != forb]
                if alt: cp, cws = zip(*alt); cp, cws = list(cp), list(cws)
            captain = random.choices(cp, weights=cws, k=1)[0]
            if cr.get("c15", True) and idx < 5:
                ar_done = any(any(p["id"] == cid and p["role"] == "All-rounder" for p in players) for cid in cap_cnt)
                if not ar_done and idx == 4:
                    arc = [p for p in cp if p["role"] == "All-rounder"]
                    if arc: captain = random.choice(arc)
            if safe_core and idx < 5:
                low_risk = [p for p in cp if p.get("risk_level") == "Low"]
                if low_risk: captain = sorted(low_risk, key=lambda p: cap_cnt[p["id"]])[0]
            vp = [p for p in players if p["id"] != captain["id"]]
            if not vp: continue
            def vw(p):
                b = risk_weight(p, mode)
                b /= (1 + vc_cnt[p["id"]] * 0.3)
                return max(b, 0.05)
            vws = [vw(p) for p in vp]
            if cr.get("c7", True):
                alt = [(p, w) for p, w in zip(vp, vws) if (captain["id"], p["id"]) not in cv_pairs]
                if alt: vp, vws = zip(*alt); vp, vws = list(vp), list(vws)
            vice_captain = random.choices(vp, weights=vws, k=1)[0]
            cv = (captain["id"], vice_captain["id"])
            if cr.get("c6", True) and len(cv_pairs) < 5 and len(result) >= 5:
                if cv in cv_pairs and attempts < 150: continue
            if adv.get("unique_cap", False):
                if captain["id"] in [r.get("_cap_id") for r in result]: continue
            if adv.get("unique_vc", False):
                if vice_captain["id"] in [r.get("_vc_id") for r in result]: continue
            valid = True
            th_set.add(h); cv_pairs.add(cv)
            cap_cnt[captain["id"]] += 1; vc_cnt[vice_captain["id"]] += 1
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


# =============================================================================
# ─── SHARED CSS ──────────────────────────────────────────────────────────────
# =============================================================================

_CSS = """
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="theme-color" content="#060810">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Barlow+Condensed:wght@400;600;700;800&family=DM+Sans:wght@300;400;500;600&display=swap" rel="stylesheet">
<style>
:root {
  --bg:#060810; --s1:#0b0e1c; --s2:#0f1220; --s3:#131728; --s4:#181c30; --s5:#1e2238;
  --brd:#1d2140; --brd2:#2a3060; --brd3:#374070;
  --gld:#f5c842; --gld2:#d4a212; --gld3:#fad96a; --gld-glow:rgba(245,200,66,.15); --gld-dim:rgba(245,200,66,.08);
  --ora:#ff7043; --grn:#00e5a0; --blu:#4db8ff; --red:#ff4d6d; --pur:#a78bfa; --cyn:#22d3ee;
  --txt:#e2e8f8; --txt2:#8896b8; --txt3:#4a5578; --txt4:#2d3555;
  --r:14px; --r2:10px; --r3:8px;
  --shadow:0 8px 32px rgba(0,0,0,.6); --shadow2:0 2px 12px rgba(0,0,0,.4);
  --glow-gld:0 0 30px rgba(245,200,66,.12),0 0 60px rgba(245,200,66,.06);
  --hdr-h:58px; --step-h:52px;
}
*,*::before,*::after{margin:0;padding:0;box-sizing:border-box;}
html{scroll-behavior:smooth;}
body{font-family:'DM Sans',-apple-system,BlinkMacSystemFont,sans-serif;background:var(--bg);color:var(--txt);min-height:100vh;overflow-x:hidden;font-size:15px;line-height:1.65;}
body.has-steps{padding-top:calc(var(--hdr-h) + var(--step-h));}
body.no-steps{padding-top:var(--hdr-h);}
body::before{content:'';position:fixed;inset:0;z-index:0;pointer-events:none;
  background-image:radial-gradient(ellipse 80% 50% at 50% -5%,rgba(245,200,66,.05),transparent 60%),
  radial-gradient(ellipse 40% 30% at 85% 110%,rgba(77,184,255,.04),transparent 50%),
  linear-gradient(rgba(255,255,255,.008) 1px,transparent 1px),
  linear-gradient(90deg,rgba(255,255,255,.008) 1px,transparent 1px);
  background-size:100%,100%,56px 56px,56px 56px;}
.z1{position:relative;z-index:1;}
::-webkit-scrollbar{width:5px;}
::-webkit-scrollbar-track{background:var(--s1);}
::-webkit-scrollbar-thumb{background:var(--brd3);border-radius:3px;}

/* ── HEADER ── */
header{position:fixed;top:0;left:0;right:0;z-index:900;height:var(--hdr-h);
  background:rgba(6,8,16,.97);backdrop-filter:blur(24px);-webkit-backdrop-filter:blur(24px);
  border-bottom:1px solid var(--brd);display:flex;align-items:center;padding:0 32px;}
.logo-wrap{display:flex;align-items:center;}
.logo{font-family:'Barlow Condensed',sans-serif;font-size:1.25rem;font-weight:800;letter-spacing:2px;white-space:nowrap;
  background:linear-gradient(135deg,var(--gld3) 0%,var(--gld) 40%,var(--ora) 100%);
  -webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text;text-decoration:none;}
.hdr-nav{margin-left:auto;display:flex;gap:4px;align-items:center;flex-wrap:wrap;}
.hdr-nav a{color:var(--txt2);text-decoration:none;font-size:.78rem;font-weight:500;padding:6px 11px;border-radius:8px;border:1px solid transparent;transition:all .18s;letter-spacing:.2px;}
.hdr-nav a:hover{color:var(--txt);background:var(--s2);border-color:var(--brd);}
.hdr-nav a.cta{background:linear-gradient(135deg,var(--gld),var(--gld2));color:#000;border-color:transparent;font-weight:700;letter-spacing:.8px;margin-left:8px;padding:7px 16px;}
.hdr-nav a.cta:hover{box-shadow:0 4px 16px var(--gld-glow);transform:translateY(-1px);}
.hdr-nav a.active{color:var(--gld);}

/* ── STEP BAR ── */
.step-bar{position:fixed;top:var(--hdr-h);left:0;right:0;z-index:850;height:var(--step-h);
  background:rgba(11,14,28,.98);backdrop-filter:blur(20px);border-bottom:1px solid var(--brd);
  display:flex;align-items:center;justify-content:center;padding:0 32px;}
.step-bar-inner{display:flex;align-items:center;width:100%;max-width:680px;}
.step{display:flex;align-items:center;gap:8px;flex:1;}
.step-num{width:26px;height:26px;border-radius:50%;border:2px solid var(--brd2);display:flex;align-items:center;justify-content:center;font-family:'Barlow Condensed',sans-serif;font-size:.75rem;font-weight:800;color:var(--txt3);flex-shrink:0;transition:all .3s;}
.step-lbl{font-size:.7rem;color:var(--txt3);transition:color .3s;white-space:nowrap;font-weight:500;}
.step-line{flex:1;height:1px;background:var(--brd);margin:0 6px;transition:background .3s;}
.step.done .step-num{background:var(--grn);border-color:var(--grn);color:#000;}
.step.done .step-lbl{color:var(--grn);}
.step.done .step-line{background:var(--grn);}
.step.active .step-num{background:var(--gld);border-color:var(--gld);color:#000;box-shadow:0 0 0 3px rgba(245,200,66,.22),0 0 14px rgba(245,200,66,.18);}
.step.active .step-lbl{color:var(--gld);font-weight:600;}

/* ── WRAP ── */
.wrap{max-width:1200px;margin:0 auto;padding:26px 20px 90px;}
.wrap-narrow{max-width:880px;margin:0 auto;padding:36px 20px 90px;}

/* ── HERO ── */
.hero{text-align:center;padding:64px 20px 48px;position:relative;overflow:hidden;}
.hero::before{content:'';position:absolute;inset:0;background:radial-gradient(ellipse 70% 60% at 50% 40%,rgba(245,200,66,.07),transparent 70%);pointer-events:none;}
.hero-badge{display:inline-flex;align-items:center;gap:8px;background:rgba(245,200,66,.1);border:1px solid rgba(245,200,66,.25);border-radius:100px;padding:6px 18px;font-size:.72rem;font-weight:700;color:var(--gld);letter-spacing:1.5px;text-transform:uppercase;margin-bottom:20px;}
.hero h1{font-family:'Barlow Condensed',sans-serif;font-size:clamp(2.2rem,5vw,3.8rem);font-weight:800;letter-spacing:2px;line-height:1.08;margin-bottom:16px;}
.hero h1 span{background:linear-gradient(135deg,var(--gld3),var(--gld),var(--ora));-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text;}
.hero p{font-size:1.05rem;color:var(--txt2);max-width:620px;margin:0 auto 28px;line-height:1.7;}
.hero-stats{display:flex;justify-content:center;gap:32px;flex-wrap:wrap;margin-top:32px;}
.hero-stat{text-align:center;}
.hero-stat strong{display:block;font-family:'Barlow Condensed',sans-serif;font-size:2rem;font-weight:800;color:var(--gld);}
.hero-stat span{font-size:.72rem;color:var(--txt3);text-transform:uppercase;letter-spacing:.8px;}

/* ── SECTION HEADINGS ── */
.sh{font-family:'Barlow Condensed',sans-serif;font-size:1rem;font-weight:700;letter-spacing:2.5px;text-transform:uppercase;color:var(--gld);margin-bottom:16px;display:flex;align-items:center;gap:12px;}
.sh::after{content:'';flex:1;height:1px;background:linear-gradient(to right,var(--brd2),transparent);}
.sh small{font-size:.62rem;color:var(--txt3);letter-spacing:1px;font-weight:400;}
.section-title{font-family:'Barlow Condensed',sans-serif;font-size:clamp(1.4rem,3vw,2rem);font-weight:800;letter-spacing:1.5px;margin-bottom:10px;}
.section-sub{color:var(--txt2);font-size:.92rem;line-height:1.7;margin-bottom:28px;max-width:700px;}

/* ── FEATURE CARDS ── */
.feature-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(230px,1fr));gap:14px;margin-bottom:32px;}
.feature-card{background:var(--s2);border:1px solid var(--brd);border-radius:var(--r);padding:22px 18px;transition:all .22s;position:relative;overflow:hidden;}
.feature-card::before{content:'';position:absolute;top:0;left:0;right:0;height:2px;background:linear-gradient(90deg,var(--gld),transparent);opacity:0;transition:opacity .22s;}
.feature-card:hover{border-color:rgba(245,200,66,.35);transform:translateY(-3px);box-shadow:var(--shadow);}
.feature-card:hover::before{opacity:1;}
.feat-icon{font-size:2rem;margin-bottom:12px;}
.feat-title{font-family:'Barlow Condensed',sans-serif;font-size:1rem;font-weight:800;letter-spacing:1px;margin-bottom:6px;}
.feat-desc{font-size:.78rem;color:var(--txt3);line-height:1.55;}

/* ── CONTENT PROSE ── */
.prose{color:var(--txt2);line-height:1.8;}
.prose h2{font-family:'Barlow Condensed',sans-serif;font-size:1.6rem;font-weight:800;letter-spacing:1.5px;color:var(--txt);margin:36px 0 12px;}
.prose h2:first-child{margin-top:0;}
.prose h3{font-family:'Barlow Condensed',sans-serif;font-size:1.15rem;font-weight:700;letter-spacing:.8px;color:var(--txt);margin:24px 0 8px;}
.prose p{margin-bottom:14px;font-size:.92rem;}
.prose ul,.prose ol{padding-left:1.6em;margin-bottom:14px;}
.prose li{margin-bottom:6px;font-size:.92rem;}
.prose strong{color:var(--txt);font-weight:600;}
.prose a{color:var(--gld);text-decoration:none;}
.prose a:hover{text-decoration:underline;}
.prose .highlight{background:rgba(245,200,66,.07);border:1px solid rgba(245,200,66,.18);border-radius:var(--r3);padding:16px 18px;margin:18px 0;}
.prose .highlight h4{font-family:'Barlow Condensed',sans-serif;font-size:.9rem;font-weight:800;letter-spacing:1px;color:var(--gld);margin-bottom:8px;}
.prose blockquote{border-left:3px solid var(--gld);padding:10px 18px;background:var(--gld-dim);border-radius:0 8px 8px 0;margin:18px 0;font-style:italic;color:var(--txt2);}

/* ── TABS ── */
.tab-bar{display:flex;gap:3px;background:var(--s1);border:1px solid var(--brd);border-radius:11px;padding:4px;width:fit-content;margin-bottom:20px;}
.tab-btn{padding:7px 18px;border-radius:8px;border:none;background:transparent;color:var(--txt3);font-family:'DM Sans',sans-serif;font-size:.8rem;font-weight:500;cursor:pointer;transition:all .2s;letter-spacing:.3px;}
.tab-btn.active{background:var(--s3);color:var(--txt);border:1px solid var(--brd2);box-shadow:var(--shadow2);}

/* ── MATCH CARDS ── */
.match-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(285px,1fr));gap:10px;margin-bottom:26px;}
.match-card{background:var(--s2);border:1px solid var(--brd);border-radius:var(--r);padding:16px 18px 14px;cursor:pointer;transition:all .22s;position:relative;overflow:hidden;}
.match-card::before{content:'';position:absolute;inset:0;background:linear-gradient(135deg,rgba(245,200,66,.04),transparent 60%);opacity:0;transition:opacity .22s;}
.match-card:hover{border-color:rgba(245,200,66,.45);transform:translateY(-3px);box-shadow:var(--shadow);}
.match-card:hover::before{opacity:1;}
.match-card.selected{border-color:var(--gld);background:var(--gld-dim);box-shadow:0 0 0 1px var(--gld),var(--shadow);}
.match-time{position:absolute;top:10px;right:10px;background:rgba(245,200,66,.1);border:1px solid rgba(245,200,66,.2);color:var(--gld);font-size:.58rem;font-weight:700;padding:2px 8px;border-radius:100px;letter-spacing:.8px;}
.match-id-tag{font-size:.6rem;color:var(--txt3);letter-spacing:.8px;text-transform:uppercase;margin-bottom:8px;}
.match-vs{font-family:'Barlow Condensed',sans-serif;font-size:1.45rem;font-weight:800;letter-spacing:1px;text-align:center;line-height:1.1;}
.match-vs em{color:var(--gld);font-style:normal;margin:0 8px;font-size:.85rem;font-weight:400;}
.match-venue{font-size:.63rem;color:var(--txt3);text-align:center;margin-top:6px;}

/* ── MODE CARDS ── */
.mode-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin-bottom:26px;}
.mode-card{border-radius:var(--r);padding:22px 16px;text-align:center;cursor:pointer;border:2px solid transparent;transition:all .25s;position:relative;overflow:hidden;}
.mode-card.safe{background:linear-gradient(145deg,#04110d,#051410);border-color:rgba(0,229,160,.18);}
.mode-card.balanced{background:linear-gradient(145deg,#040f1e,#060f1e);border-color:rgba(77,184,255,.18);}
.mode-card.risky{background:linear-gradient(145deg,#130408,#170508);border-color:rgba(255,77,109,.18);}
.mode-card:hover{transform:translateY(-4px);box-shadow:var(--shadow);}
.mode-card.active.safe{border-color:var(--grn);box-shadow:0 0 40px rgba(0,229,160,.12);}
.mode-card.active.balanced{border-color:var(--blu);box-shadow:0 0 40px rgba(77,184,255,.12);}
.mode-card.active.risky{border-color:var(--red);box-shadow:0 0 40px rgba(255,77,109,.12);}
.mode-icon{font-size:2rem;margin-bottom:9px;}
.mode-name{font-family:'Barlow Condensed',sans-serif;font-size:1.3rem;font-weight:800;letter-spacing:2px;}
.mode-card.safe .mode-name{color:var(--grn);}
.mode-card.balanced .mode-name{color:var(--blu);}
.mode-card.risky .mode-name{color:var(--red);}
.mode-desc{font-size:.7rem;color:var(--txt3);margin-top:5px;line-height:1.5;}
.mode-note{font-size:.62rem;margin-top:8px;padding:3px 10px;border-radius:6px;display:inline-block;font-weight:700;letter-spacing:.5px;}
.mode-card.safe .mode-note{background:rgba(0,229,160,.1);color:var(--grn);}
.mode-card.balanced .mode-note{background:rgba(77,184,255,.1);color:var(--blu);}
.mode-card.risky .mode-note{background:rgba(255,77,109,.1);color:var(--red);}

/* ── ADV SECTION ── */
.adv-section{background:var(--s2);border:1px solid var(--brd);border-radius:var(--r);overflow:hidden;margin-bottom:24px;}
.adv-header{background:var(--s1);border-bottom:1px solid var(--brd);padding:14px 20px;display:flex;align-items:center;justify-content:space-between;cursor:pointer;user-select:none;}
.adv-header-title{font-family:'Barlow Condensed',sans-serif;font-size:.9rem;font-weight:700;letter-spacing:1.5px;color:var(--txt);}
.adv-header-arrow{color:var(--gld);transition:transform .25s;font-size:1.1rem;}
.adv-header-arrow.open{transform:rotate(180deg);}
.adv-body{padding:20px;}
.adv-group{margin-bottom:22px;}
.adv-group:last-child{margin-bottom:0;}
.adv-group-title{font-family:'Barlow Condensed',sans-serif;font-size:.72rem;font-weight:700;letter-spacing:2px;color:var(--txt3);text-transform:uppercase;margin-bottom:12px;padding-bottom:7px;border-bottom:1px solid var(--brd);display:flex;align-items:center;gap:8px;}
.adv-group-title span{background:var(--s3);border:1px solid var(--brd2);border-radius:5px;padding:1px 8px;font-size:.6rem;color:var(--gld);letter-spacing:.8px;}
.crit-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(248px,1fr));gap:7px;}
.crit-item{background:var(--s3);border:1px solid var(--brd);border-radius:var(--r3);padding:9px 13px;display:flex;align-items:flex-start;gap:10px;cursor:pointer;transition:border-color .16s,background .16s;user-select:none;}
.crit-item:hover{border-color:rgba(245,200,66,.35);background:var(--s4);}
.crit-item:has(input:checked){border-color:rgba(245,200,66,.4);background:var(--gld-dim);}
.crit-item input[type="checkbox"]{accent-color:var(--gld);width:15px;height:15px;flex-shrink:0;cursor:pointer;margin-top:2px;}
.crit-label{font-size:.73rem;color:var(--txt);cursor:pointer;line-height:1.4;}
.crit-label small{display:block;color:var(--txt3);font-size:.62rem;margin-top:1px;}
.input-row{display:flex;gap:13px;flex-wrap:wrap;margin-bottom:18px;}
.input-group{flex:1;min-width:130px;display:flex;flex-direction:column;gap:6px;}
.input-group label{font-size:.63rem;color:var(--txt3);letter-spacing:1px;text-transform:uppercase;font-weight:600;}
.input-group input,.input-group select{background:var(--s3);border:1px solid var(--brd);border-radius:var(--r3);padding:9px 12px;color:var(--txt);font-size:.83rem;font-family:'DM Sans',sans-serif;width:100%;transition:border-color .18s;outline:none;}
.input-group input:focus,.input-group select:focus{border-color:rgba(245,200,66,.5);box-shadow:0 0 0 3px rgba(245,200,66,.07);}

/* ── BUTTONS ── */
.btn{display:inline-flex;align-items:center;justify-content:center;gap:8px;padding:10px 24px;border-radius:var(--r3);border:none;cursor:pointer;font-family:'Barlow Condensed',sans-serif;font-size:1rem;font-weight:700;letter-spacing:1px;text-decoration:none;transition:all .22s;white-space:nowrap;position:relative;overflow:hidden;}
.btn::after{content:'';position:absolute;inset:0;opacity:0;background:rgba(255,255,255,.08);transition:opacity .2s;}
.btn:hover::after{opacity:1;}
.btn-gold{background:linear-gradient(135deg,var(--gld3),var(--gld),var(--gld2));color:#000;box-shadow:0 4px 18px rgba(245,200,66,.22);}
.btn-gold:hover{transform:translateY(-2px);box-shadow:0 8px 28px rgba(245,200,66,.3);}
.btn-ora{background:linear-gradient(135deg,#ff7043,#d43200);color:#fff;box-shadow:0 4px 18px rgba(255,112,67,.25);}
.btn-ora:hover{transform:translateY(-2px);box-shadow:0 8px 28px rgba(255,112,67,.35);}
.btn-grn{background:linear-gradient(135deg,var(--grn),#00b87a);color:#000;box-shadow:0 4px 18px rgba(0,229,160,.2);}
.btn-grn:hover{transform:translateY(-2px);box-shadow:0 8px 28px rgba(0,229,160,.3);}
.btn-ghost{background:transparent;color:var(--txt3);border:1px solid var(--brd);}
.btn-ghost:hover{border-color:var(--brd3);color:var(--txt);}
.btn-row{display:flex;gap:11px;flex-wrap:wrap;margin-bottom:30px;align-items:center;}
.btn-lg{padding:14px 32px;font-size:1.1rem;border-radius:11px;letter-spacing:1.5px;}
.btn-xl{padding:16px 40px;font-size:1.2rem;border-radius:12px;letter-spacing:2px;}

/* ── PILLS ── */
.pill{padding:3px 12px;border-radius:100px;font-size:.66rem;font-weight:700;text-transform:uppercase;letter-spacing:.8px;border:1px solid transparent;}
.pill-safe{background:rgba(0,229,160,.1);color:var(--grn);border-color:rgba(0,229,160,.2);}
.pill-balanced{background:rgba(77,184,255,.1);color:var(--blu);border-color:rgba(77,184,255,.2);}
.pill-risky{background:rgba(255,77,109,.1);color:var(--red);border-color:rgba(255,77,109,.2);}
.pill-neutral{background:var(--s3);color:var(--txt3);border-color:var(--brd);}

/* ── RESULTS ── */
.stats-bar{display:flex;gap:10px;flex-wrap:wrap;margin-bottom:20px;}
.stat-chip{background:var(--s2);border:1px solid var(--brd);border-radius:11px;padding:10px 18px;text-align:center;flex:1;min-width:80px;}
.stat-chip strong{display:block;font-family:'Barlow Condensed',sans-serif;font-size:1.1rem;font-weight:800;color:var(--gld);line-height:1;}
.stat-chip span{font-size:.6rem;color:var(--txt3);text-transform:uppercase;letter-spacing:.5px;margin-top:2px;display:block;}
.res-topbar{display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:12px;margin-bottom:18px;}
.team-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(295px,1fr));gap:14px;}
.team-card{background:var(--s2);border:1px solid var(--brd);border-radius:var(--r);overflow:hidden;position:relative;transition:border-color .2s,transform .22s,box-shadow .22s;}
.team-card:hover{border-color:var(--brd3);transform:translateY(-2px);box-shadow:var(--shadow);}
.team-hdr{background:linear-gradient(135deg,var(--s3),var(--s1));padding:11px 15px;display:flex;justify-content:space-between;align-items:center;border-bottom:1px solid var(--brd);}
.team-num{font-family:'Barlow Condensed',sans-serif;font-size:.9rem;font-weight:800;color:var(--gld);letter-spacing:2px;}
.badge{font-size:.58rem;font-weight:700;padding:3px 9px;border-radius:100px;letter-spacing:.8px;text-transform:uppercase;}
.badge-free{background:var(--grn);color:#000;}
.badge-lock{background:var(--s5);color:var(--txt3);border:1px solid var(--brd2);}
.cv-row{display:flex;gap:7px;padding:11px 13px 0;}
.cv-pill{flex:1;background:var(--s3);border:1px solid var(--brd);border-radius:var(--r3);padding:7px 9px;text-align:center;}
.cv-lbl{display:block;font-size:.56rem;color:var(--txt3);letter-spacing:.4px;text-transform:uppercase;font-weight:600;margin-bottom:2px;}
.cv-nm{font-size:.76rem;font-weight:700;display:block;line-height:1.25;}
.cv-c .cv-nm{color:var(--gld);}
.cv-vc .cv-nm{color:var(--blu);}
.plist{list-style:none;padding:9px 13px 0;}
.pitem{display:flex;align-items:center;gap:7px;padding:5px 0;border-bottom:1px solid rgba(30,34,56,.8);font-size:.74rem;}
.pitem:last-child{border-bottom:none;}
.rdot{width:5px;height:5px;border-radius:50%;flex-shrink:0;}
.d-bat{background:var(--blu);}
.d-bowl{background:var(--ora);}
.d-ar{background:var(--grn);}
.d-wk{background:var(--gld);}
.pname{flex:1;color:var(--txt);}
.ct{color:var(--gld);font-size:.6rem;font-weight:800;margin-left:3px;}
.vct{color:var(--blu);font-size:.6rem;font-weight:800;margin-left:3px;}
.rtag{font-size:.58rem;font-weight:700;padding:1px 6px;border-radius:5px;flex-shrink:0;}
.rL{background:rgba(0,229,160,.1);color:var(--grn);}
.rM{background:rgba(77,184,255,.1);color:var(--blu);}
.rH{background:rgba(255,77,109,.1);color:var(--red);}
.card-foot{padding:9px 13px;border-top:1px solid var(--brd);margin-top:9px;display:flex;justify-content:space-between;align-items:center;}
.foot-info{font-size:.62rem;color:var(--txt3);}
.copy-btn{background:none;border:1px solid var(--brd);color:var(--txt3);font-size:.67rem;padding:4px 11px;border-radius:6px;cursor:pointer;transition:all .18s;font-family:'DM Sans',sans-serif;font-weight:500;}
.copy-btn:hover:not(:disabled){border-color:var(--gld);color:var(--gld);}
.copy-btn:disabled{opacity:.22;cursor:default;}
.match-strip{background:var(--s2);border:1px solid var(--brd);border-radius:var(--r);padding:16px 22px;margin-bottom:20px;display:flex;align-items:center;gap:16px;flex-wrap:wrap;}
.strip-vs{font-family:'Barlow Condensed',sans-serif;font-size:1.5rem;font-weight:800;letter-spacing:1.5px;line-height:1;}
.strip-vs em{color:var(--gld);font-style:normal;margin:0 10px;font-size:.85rem;font-weight:400;}
.strip-venue{font-size:.65rem;color:var(--txt3);margin-top:3px;}
.strip-right{margin-left:auto;display:flex;gap:8px;flex-wrap:wrap;align-items:center;}

/* ── LOCK/UNLOCK ── */
.lock-ov{position:absolute;inset:0;background:rgba(6,8,16,.88);backdrop-filter:blur(6px);-webkit-backdrop-filter:blur(6px);border-radius:var(--r);z-index:20;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:6px;transition:opacity .45s ease;}
.lock-ico{font-size:1.8rem;}
.lock-lbl{font-family:'Barlow Condensed',sans-serif;font-size:.9rem;font-weight:800;letter-spacing:2px;color:var(--txt3);}
.lock-sub{font-size:.62rem;color:var(--txt3);}
.unlock-banner{grid-column:1/-1;background:linear-gradient(135deg,rgba(20,15,2,.95),rgba(28,20,4,.95));border:2px solid rgba(245,200,66,.3);border-radius:16px;padding:28px 32px;text-align:center;position:relative;overflow:hidden;}
.unlock-banner::before{content:'';position:absolute;inset:0;background:radial-gradient(ellipse at top,rgba(245,200,66,.07),transparent 70%);pointer-events:none;}
.unlock-count{display:inline-block;background:rgba(245,200,66,.12);border:1px solid rgba(245,200,66,.28);border-radius:100px;padding:4px 16px;font-size:.68rem;color:var(--gld);font-weight:700;letter-spacing:1px;text-transform:uppercase;margin-bottom:10px;position:relative;}
.unlock-banner h3{font-family:'Barlow Condensed',sans-serif;font-size:1.6rem;font-weight:800;letter-spacing:2px;color:var(--gld);margin-bottom:6px;position:relative;}
.unlock-banner>p{color:var(--txt3);font-size:.8rem;margin-bottom:18px;position:relative;line-height:1.6;}
.unlock-perks{display:flex;justify-content:center;gap:20px;flex-wrap:wrap;margin-bottom:18px;position:relative;}
.unlock-perk{font-size:.7rem;color:var(--txt2);display:flex;align-items:center;gap:5px;}

/* ── MODAL ── */
.modal-bg{position:fixed;inset:0;background:rgba(0,0,0,.96);z-index:9000;display:flex;align-items:center;justify-content:center;opacity:0;pointer-events:none;transition:opacity .28s;}
.modal-bg.open{opacity:1;pointer-events:all;}
.modal-box{background:var(--s2);border:2px solid rgba(245,200,66,.3);border-radius:18px;padding:36px 40px;max-width:420px;width:94%;text-align:center;transform:scale(.94) translateY(16px);transition:transform .28s cubic-bezier(.34,1.56,.64,1);position:relative;overflow:hidden;}
.modal-box::before{content:'';position:absolute;top:0;left:0;right:0;height:3px;background:linear-gradient(90deg,var(--gld),var(--ora),var(--gld));}
.modal-bg.open .modal-box{transform:scale(1) translateY(0);}
.modal-box h2{font-family:'Barlow Condensed',sans-serif;font-size:1.65rem;font-weight:800;letter-spacing:2px;color:var(--gld);margin-bottom:6px;}
.modal-box>p{color:var(--txt3);font-size:.8rem;margin-bottom:18px;line-height:1.6;}
.ad-box{background:var(--s1);border:2px dashed var(--brd2);border-radius:13px;padding:24px 20px;margin:0 0 16px;}
.ad-icon{font-size:2.6rem;margin-bottom:8px;}
.ad-label{font-size:.85rem;color:var(--txt2);font-weight:600;}
.ad-sub{font-size:.68rem;color:var(--txt3);margin-top:3px;}
.ad-prog{height:7px;background:var(--brd);border-radius:100px;overflow:hidden;margin-top:16px;}
.ad-bar{height:100%;border-radius:100px;width:0%;background:linear-gradient(90deg,var(--ora),var(--gld));transition:width .15s linear;box-shadow:0 0 8px rgba(245,200,66,.4);}
.ad-tmr{font-family:'Barlow Condensed',sans-serif;font-size:1.15rem;font-weight:800;color:var(--ora);margin-top:11px;letter-spacing:1.5px;}
.modal-close-note{font-size:.67rem;color:var(--txt3);margin-top:10px;}

/* ── TOAST ── */
.toast{position:fixed;bottom:24px;right:24px;z-index:9999;padding:11px 20px;border-radius:11px;font-size:.8rem;font-weight:600;transform:translateY(56px);opacity:0;transition:all .3s cubic-bezier(.34,1.56,.64,1);pointer-events:none;box-shadow:var(--shadow);max-width:300px;}
.toast.show{transform:translateY(0);opacity:1;}

/* ── SPINNER ── */
.spinner-overlay{position:fixed;inset:0;background:rgba(6,8,16,.95);z-index:8000;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:20px;opacity:0;pointer-events:none;transition:opacity .25s;}
.spinner-overlay.active{opacity:1;pointer-events:all;}
.spinner{width:54px;height:54px;border:4px solid var(--brd2);border-top-color:var(--gld);border-radius:50%;animation:spin .85s linear infinite;}
@keyframes spin{to{transform:rotate(360deg);}}
.spinner-text{font-family:'Barlow Condensed',sans-serif;font-size:1.35rem;font-weight:800;letter-spacing:2px;color:var(--gld);}
.spinner-sub{font-size:.76rem;color:var(--txt3);}

/* ── BLOG CARDS ── */
.blog-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:18px;margin-bottom:32px;}
.blog-card{background:var(--s2);border:1px solid var(--brd);border-radius:var(--r);overflow:hidden;transition:all .22s;text-decoration:none;display:block;}
.blog-card:hover{border-color:rgba(245,200,66,.4);transform:translateY(-3px);box-shadow:var(--shadow);}
.blog-card-img{height:140px;background:linear-gradient(135deg,var(--s3),var(--s1));display:flex;align-items:center;justify-content:center;font-size:3rem;border-bottom:1px solid var(--brd);}
.blog-card-body{padding:18px;}
.blog-tag{font-size:.6rem;font-weight:700;letter-spacing:1px;text-transform:uppercase;color:var(--gld);margin-bottom:8px;display:block;}
.blog-card-title{font-family:'Barlow Condensed',sans-serif;font-size:1.1rem;font-weight:800;letter-spacing:.5px;color:var(--txt);margin-bottom:8px;line-height:1.25;}
.blog-card-excerpt{font-size:.78rem;color:var(--txt3);line-height:1.55;}
.blog-card-meta{display:flex;align-items:center;gap:10px;margin-top:12px;font-size:.65rem;color:var(--txt3);}
.blog-article-header{background:linear-gradient(135deg,var(--s2),var(--s1));border:1px solid var(--brd);border-radius:var(--r);padding:32px 36px;margin-bottom:32px;}
.blog-article-header .blog-tag{font-size:.7rem;margin-bottom:12px;}
.blog-article-header h1{font-family:'Barlow Condensed',sans-serif;font-size:clamp(1.8rem,4vw,2.8rem);font-weight:800;letter-spacing:1px;line-height:1.1;margin-bottom:12px;}
.blog-article-header .meta{font-size:.75rem;color:var(--txt3);display:flex;gap:16px;flex-wrap:wrap;}

/* ── FAQ ── */
.faq-item{background:var(--s2);border:1px solid var(--brd);border-radius:11px;margin-bottom:8px;overflow:hidden;}
.faq-q{padding:14px 17px;cursor:pointer;font-size:.88rem;font-weight:600;color:var(--txt);display:flex;justify-content:space-between;align-items:center;transition:background .18s;gap:12px;}
.faq-q:hover{background:var(--s3);}
.faq-q .arrow{color:var(--gld);font-size:1rem;transition:transform .22s;flex-shrink:0;}
.faq-q.open .arrow{transform:rotate(180deg);}
.faq-a{padding:0 17px;max-height:0;overflow:hidden;transition:max-height .32s ease,padding .32s;font-size:.85rem;color:var(--txt2);line-height:1.75;}
.faq-a.open{max-height:600px;padding:0 17px 16px;}

/* ── STRATEGY CARDS ── */
.strategy-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:14px;margin:16px 0 24px;}
.strategy-card{background:var(--s2);border:1px solid var(--brd);border-radius:var(--r);padding:20px 16px;}
.strategy-card h4{font-family:'Barlow Condensed',sans-serif;font-size:1rem;font-weight:800;margin-bottom:8px;letter-spacing:1px;}
.strategy-card p{font-size:.78rem;color:var(--txt3);line-height:1.55;margin:0;}
.strat-safe{border-top:3px solid var(--grn);}
.strat-safe h4{color:var(--grn);}
.strat-balanced{border-top:3px solid var(--blu);}
.strat-balanced h4{color:var(--blu);}
.strat-risky{border-top:3px solid var(--red);}
.strat-risky h4{color:var(--red);}

/* ── TIPS BOX ── */
.tips-box{background:rgba(0,229,160,.05);border:1px solid rgba(0,229,160,.18);border-radius:var(--r);padding:20px 22px;margin:20px 0;}
.tips-box h4{font-family:'Barlow Condensed',sans-serif;color:var(--grn);font-size:1rem;letter-spacing:1px;margin-bottom:12px;}
.tips-box ul{color:var(--txt2);font-size:.85rem;margin:0;padding-left:1.4em;}
.tips-box li{margin-bottom:6px;}
.warn-box{background:rgba(255,112,67,.05);border:1px solid rgba(255,112,67,.2);border-radius:var(--r);padding:18px 20px;margin:18px 0;}
.warn-box h4{font-family:'Barlow Condensed',sans-serif;color:var(--ora);font-size:.9rem;letter-spacing:1px;margin-bottom:10px;}
.warn-box p{font-size:.82rem;color:var(--txt2);margin:0;}

/* ── DIVIDER ── */
.divider{height:1px;background:var(--brd);margin:28px 0;}

/* ── CHIP PICKER ── */
.chip-picker{background:var(--s3);border:1px solid var(--brd);border-radius:var(--r3);padding:12px;min-height:90px;}
.chip-placeholder{font-size:.73rem;color:var(--txt3);font-style:italic;}
.chip-team-lbl{font-size:.6rem;font-weight:700;color:var(--txt3);letter-spacing:1.2px;text-transform:uppercase;margin:10px 0 6px;}
.chip-team-lbl:first-child{margin-top:0;}
.chip-row{display:flex;flex-wrap:wrap;gap:5px;margin-bottom:4px;}
.pchip{display:inline-flex;align-items:center;gap:6px;background:var(--s4);border:1px solid var(--brd2);border-radius:7px;padding:5px 11px;cursor:pointer;transition:all .16s;font-family:'DM Sans',sans-serif;user-select:none;}
.pchip:hover{border-color:rgba(245,200,66,.5);background:var(--gld-dim);}
.pchip--active{background:var(--gld-dim);border-color:var(--gld);box-shadow:0 0 0 1px var(--gld);}
.pchip--active-excl{background:rgba(255,77,109,.12);border-color:var(--red);box-shadow:0 0 0 1px var(--red);}
.pchip-name{font-size:.73rem;color:var(--txt);font-weight:500;line-height:1;}
.pchip-role{font-size:.58rem;color:var(--txt3);background:var(--s1);border-radius:4px;padding:1px 6px;}
.pchip--active .pchip-name{color:var(--gld);}
.pchip--active .pchip-role{color:var(--gld);background:rgba(245,200,66,.1);}
.pchip--active-excl .pchip-name{color:var(--red);}
.pchip--active-excl .pchip-role{color:var(--red);background:rgba(255,77,109,.1);}
.chip-summary{font-size:.7rem;margin-top:8px;min-height:18px;line-height:1.5;}
.alert-sel{background:rgba(245,200,66,.06);border:1px solid rgba(245,200,66,.2);border-radius:var(--r3);padding:10px 14px;font-size:.8rem;color:var(--txt2);margin-bottom:16px;display:none;line-height:1.5;}

/* ── AGE GATE ── */
.age-gate-overlay{position:fixed;inset:0;z-index:99999;background:rgba(4,5,12,.97);backdrop-filter:blur(18px);-webkit-backdrop-filter:blur(18px);display:flex;align-items:center;justify-content:center;padding:20px;}
.age-gate-box{background:var(--s2);border:1px solid var(--brd2);border-radius:20px;padding:44px 40px 36px;max-width:420px;width:100%;text-align:center;position:relative;overflow:hidden;box-shadow:0 24px 80px rgba(0,0,0,.7);animation:fadeUp .35s ease both;}
.age-gate-box::before{content:'';position:absolute;top:0;left:0;right:0;height:3px;background:linear-gradient(90deg,var(--gld3),var(--gld),var(--ora));}
.age-gate-badge{display:inline-flex;align-items:center;justify-content:center;width:64px;height:64px;border-radius:50%;background:linear-gradient(135deg,rgba(245,200,66,.15),rgba(245,200,66,.05));border:2px solid rgba(245,200,66,.3);font-size:1.9rem;margin-bottom:18px;}
.age-gate-box h2{font-family:'Barlow Condensed',sans-serif;font-size:1.75rem;font-weight:800;letter-spacing:2px;color:var(--txt);margin-bottom:8px;}
.age-gate-box p{font-size:.85rem;color:var(--txt3);line-height:1.65;margin-bottom:24px;}
.age-gate-btn-row{display:flex;gap:12px;justify-content:center;}
.age-gate-yes{flex:1;padding:14px 20px;border:none;border-radius:11px;cursor:pointer;font-family:'Barlow Condensed',sans-serif;font-size:1.1rem;font-weight:800;letter-spacing:1.5px;transition:all .22s;background:linear-gradient(135deg,var(--gld3),var(--gld),var(--gld2));color:#000;box-shadow:0 6px 22px rgba(245,200,66,.3);}
.age-gate-yes:hover{transform:translateY(-2px);box-shadow:0 10px 32px rgba(245,200,66,.45);}
.age-gate-no{padding:14px 20px;border:1px solid var(--brd2);border-radius:11px;cursor:pointer;font-family:'Barlow Condensed',sans-serif;font-size:1rem;font-weight:600;letter-spacing:1px;transition:all .2s;background:transparent;color:var(--txt3);min-width:90px;}
.age-gate-no:hover{border-color:var(--red);color:var(--red);}
.age-gate-note{font-size:.65rem;color:var(--txt4);margin-top:16px;line-height:1.5;}
.age-gate-blocked{position:fixed;inset:0;z-index:99999;background:rgba(4,5,12,.99);display:none;align-items:center;justify-content:center;flex-direction:column;gap:14px;text-align:center;padding:28px;}
.age-gate-blocked h3{font-family:'Barlow Condensed',sans-serif;font-size:1.4rem;font-weight:800;letter-spacing:2px;color:var(--red);}
.age-gate-blocked p{color:var(--txt3);font-size:.85rem;max-width:340px;}

/* ── SUCCESS BANNER ── */
.success-banner{background:linear-gradient(135deg,rgba(0,229,160,.08),rgba(0,229,160,.04));border-bottom:1px solid rgba(0,229,160,.18);padding:12px 28px;display:flex;align-items:center;gap:14px;font-size:.82rem;color:var(--txt2);}
.success-banner strong{color:var(--grn);display:block;font-size:.88rem;margin-bottom:1px;}
.success-sub{font-size:.73rem;color:var(--txt3);}

/* ── LEGAL / CONTACT ── */
.legal-wrap{max-width:820px;margin:0 auto;padding:42px 22px 90px;}
.legal-wrap h1{font-family:'Barlow Condensed',sans-serif;font-size:2rem;font-weight:800;letter-spacing:3px;color:var(--gld);margin-bottom:6px;}
.legal-wrap .last-updated{font-size:.7rem;color:var(--txt3);margin-bottom:28px;}
.legal-wrap h2{font-family:'Barlow Condensed',sans-serif;font-size:1.05rem;font-weight:700;color:var(--txt);margin:24px 0 8px;}
.legal-wrap p{font-size:.85rem;color:var(--txt2);line-height:1.75;margin-bottom:12px;}
.legal-wrap ul{font-size:.85rem;color:var(--txt2);line-height:1.75;padding-left:1.5em;margin-bottom:12px;}
.legal-wrap li{margin-bottom:4px;}
.legal-wrap a{color:var(--gld);text-decoration:none;}
.contact-form{display:flex;flex-direction:column;gap:15px;max-width:560px;}
.form-group{display:flex;flex-direction:column;gap:6px;}
.form-group label{font-size:.7rem;color:var(--txt3);letter-spacing:1px;text-transform:uppercase;font-weight:600;}
.form-group input,.form-group textarea,.form-group select{background:var(--s2);border:1px solid var(--brd);border-radius:var(--r3);padding:10px 13px;color:var(--txt);font-size:.85rem;font-family:'DM Sans',sans-serif;outline:none;transition:border-color .18s;}
.form-group input:focus,.form-group textarea:focus{border-color:rgba(245,200,66,.5);box-shadow:0 0 0 3px rgba(245,200,66,.07);}
.form-group textarea{resize:vertical;min-height:120px;}

/* ── FOOTER ── */
footer{background:var(--s1);border-top:1px solid var(--brd);padding:36px 28px 24px;margin-top:64px;}
.footer-grid{max-width:1200px;margin:0 auto;display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:24px;margin-bottom:24px;}
.footer-col h4{font-family:'Barlow Condensed',sans-serif;font-size:.9rem;font-weight:800;letter-spacing:1.5px;color:var(--gld);margin-bottom:10px;}
.footer-col p,.footer-col a{font-size:.74rem;color:var(--txt3);display:block;margin-bottom:5px;text-decoration:none;transition:color .18s;line-height:1.6;}
.footer-col a:hover{color:var(--txt);}
.footer-bottom{max-width:1200px;margin:0 auto;padding-top:18px;border-top:1px solid var(--brd);display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:10px;}
.footer-bottom p{font-size:.68rem;color:var(--txt3);}
.footer-disclaimer{font-size:.67rem;color:var(--txt3);line-height:1.6;max-width:1200px;margin:16px auto 0;text-align:center;}
.footer-trust{display:flex;gap:10px;flex-wrap:wrap;justify-content:center;margin-bottom:16px;}
.trust-badge{background:var(--s2);border:1px solid var(--brd);border-radius:8px;padding:5px 13px;font-size:.65rem;color:var(--txt3);letter-spacing:.5px;}

/* ── ANIMATIONS ── */
@keyframes fadeUp{from{opacity:0;transform:translateY(16px);}to{opacity:1;transform:translateY(0);}}
.fade-up{animation:fadeUp .38s ease both;}

/* ── ACCESSIBILITY ── */
.skip-link{position:absolute;top:-50px;left:18px;z-index:9999;background:var(--gld);color:#000;padding:8px 18px;border-radius:0 0 9px 9px;font-size:.82rem;font-weight:700;text-decoration:none;transition:top .2s;}
.skip-link:focus{top:0;}
:focus-visible{outline:2px solid var(--gld);outline-offset:2px;border-radius:4px;}

/* ── RESPONSIVE ── */
@media(max-width:768px){
  :root{--hdr-h:52px;--step-h:44px;}
  body{font-size:14px;}
  header{padding:0 14px;}
  .logo{font-size:1.05rem;}
  .hdr-nav a:not(.cta):not(.active){display:none;}
  .step-lbl{display:none;}
  .step-line{margin:0 4px;}
  .step-bar{padding:0 12px;}
  .wrap{padding:14px 12px 60px;}
  .wrap-narrow{padding:20px 14px 60px;}
  .match-grid{grid-template-columns:1fr;}
  .mode-grid{grid-template-columns:1fr;gap:8px;}
  .team-grid{grid-template-columns:1fr;}
  .blog-grid{grid-template-columns:1fr;}
  .strategy-grid{grid-template-columns:1fr;}
  .feature-grid{grid-template-columns:1fr;}
  .btn-xl{padding:13px 22px;font-size:1rem;}
  .btn-row{flex-direction:column;gap:8px;}
  .btn-row .btn{width:100%;justify-content:center;}
  .match-strip{flex-direction:column;gap:10px;}
  .strip-right{margin-left:0;}
  .hero{padding:40px 16px 32px;}
  .hero-stats{gap:20px;}
  .adv-body{padding:14px;}
  .input-row{flex-direction:column;gap:10px;}
  .crit-grid{grid-template-columns:1fr;}
  .modal-box{padding:22px 16px;margin:0 10px;}
  .footer-grid{grid-template-columns:1fr;gap:18px;}
  .footer-bottom{flex-direction:column;text-align:center;}
  .blog-article-header{padding:20px;}
  div[style*="grid-template-columns:1fr 1fr"]{display:grid!important;grid-template-columns:1fr!important;gap:12px!important;}
  .age-gate-box{padding:30px 20px 24px;}
  .age-gate-btn-row{flex-direction:column;}
  .age-gate-yes,.age-gate-no{width:100%;}
}
@media(max-width:380px){
  .logo{font-size:.92rem;}
  .match-vs{font-size:1.05rem;}
}
@media print{
  header,.step-bar,.unlock-banner,.btn,.copy-btn,.lock-ov,.modal-bg,.toast,footer,.spinner-overlay{display:none!important;}
  body{background:#fff;color:#000;padding-top:0;}
  .team-card{border:1px solid #ccc;break-inside:avoid;background:#fff;}
  .pname{color:#000;}
  .cv-nm{color:#b8860b!important;}
}
</style>
<script async src="https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client=ca-pub-9904803540658016" crossorigin="anonymous"></script>
<script async src="https://www.googletagmanager.com/gtag/js?id=G-VJS4H89EKW"></script>
<script>
  window.dataLayer=window.dataLayer||[];
  function gtag(){dataLayer.push(arguments);}
  gtag('js',new Date());
  gtag('config','G-VJS4H89EKW');
</script>
"""

# ─── SHARED HEADER ────────────────────────────────────────────────────────────
def _header(active=""):
    return f"""
<a href="#main" class="skip-link">Skip to content</a>
<header role="banner">
  <div class="logo-wrap">
    <a href="/" class="logo">⚡ FantasyXI AI</a>
  </div>
  <nav class="hdr-nav" aria-label="Main navigation">
    <a href="/" {"class='active'" if active=="home" else ""}>Generator</a>
    <a href="/fantasy-cricket-guide" {"class='active'" if active=="guide" else ""}>Cricket Guide</a>
    <a href="/dream11-strategy" {"class='active'" if active=="strategy" else ""}>Strategy</a>
    <a href="/blog" {"class='active'" if active=="blog" else ""}>Blog</a>
    <a href="/about" {"class='active'" if active=="about" else ""}>About</a>
    <a href="/" class="cta">🤖 Generate Teams</a>
  </nav>
</header>"""

# ─── FOOTER ───────────────────────────────────────────────────────────────────
_FOOTER = """
<footer>
  <div class="footer-grid z1">
    <div class="footer-col">
      <h4>⚡ FantasyXI AI</h4>
      <p>India's #1 AI Fantasy Cricket Team Generator. 20 unique teams for IPL, T20 World Cup, and all major tournaments — in seconds.</p>
    </div>
    <div class="footer-col">
      <h4>Generator</h4>
      <a href="/">🤖 AI Team Generator</a>
      <a href="/fantasy-cricket-guide">📖 Cricket Guide</a>
      <a href="/dream11-strategy">🏆 Dream11 Strategy</a>
      <a href="/captain-vc-strategy">👑 Captain & VC Tips</a>
    </div>
    <div class="footer-col">
      <h4>Blog</h4>
      <a href="/blog">📝 All Articles</a>
      <a href="/blog/how-to-win-dream11-grand-league">Grand League Guide</a>
      <a href="/blog/fantasy-cricket-beginners-guide">Beginner's Guide</a>
      <a href="/blog/best-captain-vc-combinations">Captain Combos</a>
    </div>
    <div class="footer-col">
      <h4>Company</h4>
      <a href="/about">ℹ️ About Us</a>
      <a href="/contact">✉️ Contact</a>
      <a href="/privacy">🔒 Privacy Policy</a>
      <a href="/terms">📋 Terms & Conditions</a>
      <a href="/disclaimer">⚠️ Disclaimer</a>
    </div>
  </div>
  <div class="footer-trust z1">
    <span class="trust-badge">🔒 Privacy First</span>
    <span class="trust-badge">🚫 No Login Required</span>
    <span class="trust-badge">⚡ Instant Generation</span>
    <span class="trust-badge">📊 Smart AI Algorithm</span>
    <span class="trust-badge">🆓 Free to Use</span>
  </div>
  <div class="footer-bottom z1">
    <p>© 2026 FantasyXI AI. All rights reserved. Not affiliated with ICC, BCCI, Dream11, or any official cricket body.</p>
    <p>For entertainment & informational purposes only.</p>
  </div>
  <div class="footer-disclaimer z1">
    ⚠️ Fantasy sports involve financial risk. Please play responsibly. FantasyXI AI does not guarantee any winnings.
    Check local laws before participating in paid fantasy sports contests. This tool is for users 18 years and above only.
  </div>
</footer>
"""

# ─── AD MODAL ─────────────────────────────────────────────────────────────────
_AD_MODAL = """
<div class="modal-bg" id="adModal" aria-modal="true" role="dialog" aria-labelledby="adModalTitle">
  <div class="modal-box">
    <h2 id="adModalTitle">📺 Quick Ad</h2>
    <p>Watch this 5-second ad to unlock all remaining teams — completely free.</p>
    <div class="ad-box">
      <div class="ad-icon">🎬</div>
      <div class="ad-label">Advertisement</div>
      <div class="ad-sub">5 seconds · No payment required</div>
      <div class="ad-prog"><div class="ad-bar" id="adBar"></div></div>
      <div class="ad-tmr" id="adTmr">⏳ 5s remaining</div>
    </div>
    <p class="modal-close-note" id="closeNote">Please wait — your teams are almost ready…</p>
  </div>
</div>
<div class="toast" id="toast" role="status" aria-live="polite"></div>
"""

# ─── SHARED JS ────────────────────────────────────────────────────────────────
_SHARED_JS = """
<script>
function showToast(msg,color){
  color=color||'#00e5a0';
  var t=document.getElementById('toast');if(!t)return;
  t.textContent=msg;t.style.background=color;
  t.style.color=(color==='#00e5a0'||color==='#f5c842')?'#000':'#fff';
  t.classList.add('show');setTimeout(function(){t.classList.remove('show');},3400);
}
function scrollToId(id){
  var el=document.getElementById(id);if(!el)return;
  var offset=58+52+12;
  var y=el.getBoundingClientRect().top+window.pageYOffset-offset;
  window.scrollTo({top:y,behavior:'smooth'});
}
function toggleFaq(el){
  var a=el.nextElementSibling;
  var isOpen=el.classList.contains('open');
  document.querySelectorAll('.faq-q').forEach(function(q){q.classList.remove('open');if(q.nextElementSibling)q.nextElementSibling.classList.remove('open');});
  if(!isOpen){el.classList.add('open');if(a)a.classList.add('open');}
}
var adInterval=null,adCountdown=5,adRunning=false;
function openAd(){
  if(adRunning)return;
  var modal=document.getElementById('adModal');if(!modal)return;
  adCountdown=5;adRunning=true;
  var bar=document.getElementById('adBar'),tmr=document.getElementById('adTmr'),note=document.getElementById('closeNote');
  if(bar)bar.style.width='0%';if(tmr)tmr.textContent='⏳ 5s remaining';
  if(note)note.textContent='Please wait — your teams are almost ready…';
  modal.classList.add('open');
  if(adInterval){clearInterval(adInterval);adInterval=null;}
  adInterval=setInterval(function(){
    adCountdown--;
    var pct=((5-adCountdown)/5*100).toFixed(1);
    if(bar)bar.style.width=pct+'%';
    if(adCountdown>0){if(tmr)tmr.textContent='⏳ '+adCountdown+'s remaining';}
    else{
      if(tmr)tmr.textContent='✅ Complete!';
      if(note)note.textContent='Unlocking your teams now…';
      clearInterval(adInterval);adInterval=null;
      setTimeout(function(){modal.classList.remove('open');adRunning=false;doUnlock();},700);
    }
  },1000);
}
function doUnlock(){
  fetch('/unlock',{method:'POST',headers:{'Content-Type':'application/json'}})
    .then(function(r){return r.json();})
    .then(function(d){
      if(!d.success){showToast('Error unlocking. Please try again.','#ff4d6d');return;}
      document.querySelectorAll('.lock-ov').forEach(function(el){el.style.opacity='0';setTimeout(function(){if(el.parentNode)el.parentNode.removeChild(el);},480);});
      document.querySelectorAll('.copy-btn').forEach(function(b){b.disabled=false;});
      document.querySelectorAll('.badge-lock').forEach(function(b){b.textContent='✓ UNLOCKED';b.classList.remove('badge-lock');b.classList.add('badge-free');});
      var banner=document.getElementById('unlockBanner');
      if(banner){
        var total=document.querySelectorAll('.team-card').length;
        banner.innerHTML='<div class="unlock-count" style="position:relative;">ALL '+total+' TEAMS UNLOCKED</div>'
          +'<h3 style="color:var(--grn);position:relative;">✅ Fully Unlocked!</h3>'
          +'<p style="position:relative;color:var(--txt2);">All teams ready. Download a PDF below.</p>'
          +'<div style="position:relative;margin-top:4px;"><a href="/export_pdf" class="btn btn-grn btn-lg">📄 Export All as PDF</a></div>';
      }
      var pBtn=document.getElementById('pdfBtn');if(pBtn)pBtn.style.display='inline-flex';
      showToast('🎉 All teams unlocked!','#f5c842');
    })
    .catch(function(){showToast('Network error. Please retry.','#ff4d6d');});
}
function copyTeam(idx){
  var cards=document.querySelectorAll('.team-card');var card=cards[idx];if(!card)return;
  var num=card.querySelector('.team-num')?card.querySelector('.team-num').textContent:'';
  var nms=card.querySelectorAll('.cv-nm');
  var cap=nms[0]?nms[0].textContent.trim():'';var vc=nms[1]?nms[1].textContent.trim():'';
  var txt=num+'\\nCaptain (2x): '+cap+'\\nVC (1.5x): '+vc+'\\n\\nPlayers:\\n';
  card.querySelectorAll('.pname').forEach(function(s){txt+=s.textContent.replace(/\\s+/g,' ').trim()+'\\n';});
  if(navigator.clipboard){navigator.clipboard.writeText(txt).then(function(){showToast('📋 Team '+(idx+1)+' copied!');});}
  else{var ta=document.createElement('textarea');ta.value=txt;document.body.appendChild(ta);ta.select();document.execCommand('copy');document.body.removeChild(ta);showToast('📋 Team '+(idx+1)+' copied!');}
}
</script>
"""


# =============================================================================
# ─── HOME PAGE ───────────────────────────────────────────────────────────────
# =============================================================================

HOME_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<title>AI Fantasy Cricket Team Generator — 20 Unique Teams | IPL, Dream11, T20 World Cup 2026</title>
<meta name="description" content="Generate 20 unique AI-powered fantasy cricket teams instantly for IPL, T20 World Cup, ICC tournaments and Dream11. Smart Safe/Balanced/Risky modes, captain rotation, exposure control. 100% free.">
<meta name="keywords" content="AI fantasy team generator, dream11 team generator, fantasy cricket teams, IPL fantasy, T20 World Cup fantasy, cricket team generator AI, dream11 AI teams 2026">
<meta name="robots" content="index,follow">
<meta property="og:title" content="AI Fantasy Cricket Team Generator — 20 AI Teams for Dream11 & IPL">
<meta property="og:description" content="Generate 20 unique AI-powered fantasy cricket teams for any match. Free, instant, smart algorithm.">
<meta property="og:type" content="website">
<meta property="og:url" content="https://fantasyxi.in/">
<link rel="canonical" href="https://fantasyxi.in/">
<script type="application/ld+json">
{"@context":"https://schema.org","@type":"WebApplication","name":"FantasyXI AI Team Generator",
"description":"AI-powered fantasy cricket team generator for IPL, Dream11, T20 World Cup",
"url":"https://fantasyxi.in","applicationCategory":"SportsApplication","isAccessibleForFree":true,
"offers":{"@type":"Offer","price":"0","priceCurrency":"INR"}}</script>
""" + _CSS + """
</head>
<body class="has-steps">

<div class="age-gate-overlay" id="ageGate" role="dialog" aria-modal="true">
  <div class="age-gate-box">
    <div class="age-gate-badge">🔞</div>
    <h2>Age Verification</h2>
    <p>FantasyXI AI contains fantasy sports content. You must be 18 years or older to continue.</p>
    <p style="font-weight:600;color:var(--txt);font-size:.9rem;">Are you 18 years or older?</p>
    <div class="age-gate-btn-row">
      <button class="age-gate-yes" onclick="ageConfirm(true)">✓ Yes, I'm 18+</button>
      <button class="age-gate-no" onclick="ageConfirm(false)">No</button>
    </div>
    <p class="age-gate-note">By clicking "Yes, I'm 18+", you confirm you are of legal age in your jurisdiction.</p>
  </div>
</div>
<div class="age-gate-blocked" id="ageBlocked">
  <h3>Access Restricted</h3>
  <p>You must be 18 years or older to use FantasyXI AI.</p>
</div>

<div class="spinner-overlay" id="spinnerOverlay" role="status" aria-live="polite">
  <div class="spinner"></div>
  <div class="spinner-text">Generating Teams…</div>
  <div class="spinner-sub">Running smart AI distribution engine</div>
</div>

""" + _header("home") + """

<div class="step-bar" id="stepBar" aria-label="Progress steps">
  <div class="step-bar-inner">
    <div class="step" id="step1"><div class="step-num">1</div><span class="step-lbl">Select Match</span><div class="step-line"></div></div>
    <div class="step" id="step2"><div class="step-num">2</div><span class="step-lbl">Choose Mode</span><div class="step-line"></div></div>
    <div class="step" id="step3"><div class="step-num">3</div><span class="step-lbl">Set Criteria</span><div class="step-line"></div></div>
    <div class="step" id="step4"><div class="step-num">4</div><span class="step-lbl">Generate</span></div>
  </div>
</div>

<main id="main">

<!-- HERO -->
<section class="hero z1">
  <div class="hero-badge">🤖 AI-Powered · Free · Instant</div>
  <h1>Generate <span>20 Unique</span><br>Fantasy Cricket Teams</h1>
  <p>India's smartest AI fantasy team generator for IPL, T20 World Cup, Dream11 and all major cricket tournaments. Safe, Balanced, and Risky modes — zero duplicates, guaranteed.</p>
  <div style="display:flex;gap:12px;justify-content:center;flex-wrap:wrap;">
    <a href="#tool" class="btn btn-gold btn-xl" onclick="scrollToId('tool')">🤖 Start Generating Free →</a>
    <a href="/fantasy-cricket-guide" class="btn btn-ghost btn-lg">📖 Learn How It Works</a>
  </div>
  <div class="hero-stats">
    <div class="hero-stat"><strong>20</strong><span>AI Teams</span></div>
    <div class="hero-stat"><strong>3</strong><span>Game Modes</span></div>
    <div class="hero-stat"><strong>0</strong><span>Duplicates</span></div>
    <div class="hero-stat"><strong>100%</strong><span>Free</span></div>
  </div>
</section>

<!-- FEATURE CARDS -->
<section class="wrap z1" style="padding-top:0;padding-bottom:0;">
  <div class="feature-grid">
    <div class="feature-card"><div class="feat-icon">🤖</div><div class="feat-title">AI Algorithm</div><div class="feat-desc">Multi-layer probability weighting with risk-adjusted player sampling and intelligent C/VC rotation.</div></div>
    <div class="feature-card"><div class="feat-icon">🛡</div><div class="feat-title">Safe / Balanced / Risky</div><div class="feat-desc">Three AI modes tailored for small leagues, mid-size contests, and IPL mega grand leagues.</div></div>
    <div class="feature-card"><div class="feat-icon">🔒</div><div class="feat-title">Lock & Exclude</div><div class="feat-desc">Lock must-have players to appear in every team or exclude players you don't trust.</div></div>
    <div class="feature-card"><div class="feat-icon">📊</div><div class="feat-title">Exposure Control</div><div class="feat-desc">Set player exposure limits so no single pick dominates your entire portfolio.</div></div>
    <div class="feature-card"><div class="feat-icon">🎯</div><div class="feat-title">Differential Injection</div><div class="feat-desc">Automatically boosts low-ownership differential picks in your last 10 teams.</div></div>
    <div class="feature-card"><div class="feat-icon">📄</div><div class="feat-title">PDF Export</div><div class="feat-desc">Download all 20 teams as a clean, formatted PDF for offline reference and entry.</div></div>
  </div>
</section>

<!-- GENERATOR TOOL -->
<section class="wrap z1" id="tool">

  <div class="tab-bar" role="tablist">
    <button class="tab-btn active" onclick="showTab('up',this)" role="tab" aria-selected="true">📅 Upcoming Matches</button>
    <button class="tab-btn" onclick="showTab('man',this)" role="tab" aria-selected="false">⚙ Manual Selection</button>
  </div>

  <div id="tab-up">
    <h2 class="sh">Select a Match <small>Step 1</small></h2>
    <div class="match-grid" role="list">
    {% for m in matches %}
      <div class="match-card" role="listitem" tabindex="0"
        onclick="selectMatch('{{m.match_id}}','{{m.team1}}','{{m.team2}}','{{m.date}}','{{m.venue|replace(chr(39),chr(32))}}',this)"
        onkeydown="if(event.key==='Enter')this.click()">
        <div class="match-time">{{m.time}}</div>
        <div class="match-id-tag">📅 {{m.date}} · {{m.match_id}}</div>
        <div class="match-vs">{{m.team1}}<em>VS</em>{{m.team2}}</div>
        <div class="match-venue">📍 {{m.venue}}</div>
      </div>
    {% endfor %}
    </div>
    <div class="alert-sel" id="selInfo" role="status"></div>
  </div>

  <div id="tab-man" style="display:none;">
    <div class="sh">Manual Team Selection</div>
    <div class="input-row">
      <div class="input-group"><label for="mt1">Team 1</label><select id="mt1">{% for t in all_teams %}<option value="{{t.team}}">{{t.team}}</option>{% endfor %}</select></div>
      <div class="input-group"><label for="mt2">Team 2</label><select id="mt2">{% for t in all_teams %}<option value="{{t.team}}"{% if loop.index==2 %} selected{% endif %}>{{t.team}}</option>{% endfor %}</select></div>
    </div>
    <button class="btn btn-ghost" onclick="setManual()">Confirm Teams →</button>
  </div>

  <div class="divider"></div>

  <h2 class="sh">AI Generation Mode <small>Step 2</small></h2>
  <div class="mode-grid" role="radiogroup">
    <div class="mode-card safe" role="radio" aria-checked="false" tabindex="0" onclick="selectMode('safe',this)" onkeydown="if(event.key==='Enter'||event.key===' ')selectMode('safe',this)">
      <div class="mode-icon">🛡</div><div class="mode-name">Safe</div>
      <div class="mode-desc">Low-risk captains · Consistent picks · Minimise variance</div>
      <div class="mode-note">✓ Best for H2H &amp; small leagues</div>
    </div>
    <div class="mode-card balanced" role="radio" aria-checked="false" tabindex="0" onclick="selectMode('balanced',this)" onkeydown="if(event.key==='Enter'||event.key===' ')selectMode('balanced',this)">
      <div class="mode-icon">⚖️</div><div class="mode-name">Balanced</div>
      <div class="mode-desc">Mixed risk · Smart C/VC rotation · Best of both worlds</div>
      <div class="mode-note">✓ Best for mid-size contests</div>
    </div>
    <div class="mode-card risky" role="radio" aria-checked="false" tabindex="0" onclick="selectMode('risky',this)" onkeydown="if(event.key==='Enter'||event.key===' ')selectMode('risky',this)">
      <div class="mode-icon">🔥</div><div class="mode-name">Risky</div>
      <div class="mode-desc">High-risk differentials · Max ceiling · Stand out from field</div>
      <div class="mode-note">✓ Best for IPL mega contests</div>
    </div>
  </div>

  <div class="btn-row" style="margin-top:6px;margin-bottom:10px;">
    <button class="btn btn-gold btn-xl" id="generateBtn" onclick="doGenerate()">🤖 Generate AI Teams</button>
    <button class="btn btn-ghost" onclick="resetAll()">↺ Reset All</button>
  </div>

  <h2 class="sh">Advanced Criteria <small>Step 3 · Optional</small></h2>
  <div class="adv-section">
    <div class="adv-header" onclick="toggleAdv(this)" role="button" aria-expanded="true">
      <span class="adv-header-title">⚙️ Configuration Engine — Power Options</span>
      <span class="adv-header-arrow open">▼</span>
    </div>
    <div class="adv-body" id="advBody">
      <div class="adv-group">
        <div class="adv-group-title">⚙️ Generation Settings <span>CORE</span></div>
        <div class="input-row">
          <div class="input-group"><label for="nt">Teams to Generate (max 20)</label><input type="number" id="nt" value="20" min="5" max="20"></div>
          <div class="input-group"><label for="max_from_one">Max Players from One Team</label><input type="number" id="max_from_one" value="7" min="5" max="10"></div>
        </div>
        <div class="input-row">
          <div class="input-group"><label>Exposure Limit (%) <span style="color:var(--gld);font-weight:700;" id="exposureVal">75%</span></label><input type="range" id="exposure" value="75" min="10" max="100" oninput="document.getElementById('exposureVal').textContent=this.value+'%'"></div>
          <div class="input-group"><label>Risk Intensity <span style="color:var(--gld);font-weight:700;" id="riskIntVal">1.0×</span></label><input type="range" id="risk_intensity" value="10" min="5" max="25" oninput="document.getElementById('riskIntVal').textContent=(this.value/10).toFixed(1)+'×'"></div>
          <div class="input-group"><label>Randomisation <span style="color:var(--gld);font-weight:700;" id="randVal">Medium</span></label><input type="range" id="rand_strength" value="5" min="0" max="10" oninput="document.getElementById('randVal').textContent=['Off','Very Low','Low','Low-Med','Medium','Medium','Med-High','High','High','Very High','Max'][this.value]"></div>
        </div>
      </div>
      <div class="adv-group">
        <div class="adv-group-title">👑 Captain &amp; Vice-Captain Rules <span>STRATEGY</span></div>
        <div class="crit-grid">
          <label class="crit-item"><input type="checkbox" id="c6" checked><div class="crit-label">At least 5 unique C/VC combinations<small>Ensures diversity</small></div></label>
          <label class="crit-item"><input type="checkbox" id="c7" checked><div class="crit-label">Avoid same C/VC pair repeating<small>No duplicate combos</small></div></label>
          <label class="crit-item"><input type="checkbox" id="c8" checked><div class="crit-label">Risk-based captain weighting<small>Mode affects captain pool</small></div></label>
          <label class="crit-item"><input type="checkbox" id="c11" checked><div class="crit-label">Prevent same captain &gt;3 consecutive<small>Rotates captain intelligently</small></div></label>
          <label class="crit-item"><input type="checkbox" id="c15" checked><div class="crit-label">≥1 All-rounder captain in first 5<small>Guaranteed AR captaincy</small></div></label>
          <label class="crit-item"><input type="checkbox" id="unique_cap"><div class="crit-label">Unique captain per team<small>No captain repeats</small></div></label>
          <label class="crit-item"><input type="checkbox" id="unique_vc"><div class="crit-label">Unique vice-captain per team<small>No VC repeats</small></div></label>
        </div>
      </div>
      <div class="adv-group">
        <div class="adv-group-title">🏏 Team Composition <span>STRUCTURE</span></div>
        <div class="crit-grid">
          <label class="crit-item"><input type="checkbox" id="c1" checked><div class="crit-label">6:5 team-split rotation<small>Alternates which team has 6</small></div></label>
          <label class="crit-item"><input type="checkbox" id="c12" checked><div class="crit-label">No identical combination<small>100% unique teams</small></div></label>
          <label class="crit-item"><input type="checkbox" id="c13" checked><div class="crit-label">Max players from one team<small>Uses setting above</small></div></label>
          <label class="crit-item"><input type="checkbox" id="c14" checked><div class="crit-label">Role constraints (WK/BAT/AR/BOWL)<small>Valid fantasy composition</small></div></label>
          <label class="crit-item"><input type="checkbox" id="differential"><div class="crit-label">Differential injection (last 10 teams)<small>Boosts low-ownership picks</small></div></label>
        </div>
        <div class="input-row" style="margin-top:14px;margin-bottom:0;">
          <div class="input-group"><label>Min Differential Players per Team</label><input type="number" id="min_diff" value="0" min="0" max="5"></div>
        </div>
      </div>
      <div class="adv-group">
        <div class="adv-group-title">🎯 Player Controls — Lock &amp; Exclude <span>PRECISION</span></div>
        <p style="font-size:.72rem;color:var(--txt3);margin-bottom:14px;">Select a match first. Click chip to <strong style="color:var(--grn);">lock</strong> or <strong style="color:var(--red);">exclude</strong>.</p>
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:18px;">
          <div>
            <div style="font-size:.68rem;font-weight:700;color:var(--grn);letter-spacing:.9px;text-transform:uppercase;margin-bottom:8px;">🔒 Lock Players</div>
            <div id="lock_picker" class="chip-picker"><span class="chip-placeholder">Select a match first</span></div>
            <div id="lock_summary" class="chip-summary"></div>
          </div>
          <div>
            <div style="font-size:.68rem;font-weight:700;color:var(--red);letter-spacing:.9px;text-transform:uppercase;margin-bottom:8px;">🚫 Exclude Players</div>
            <div id="excl_picker" class="chip-picker"><span class="chip-placeholder">Select a match first</span></div>
            <div id="excl_summary" class="chip-summary"></div>
          </div>
        </div>
      </div>
    </div>
  </div>
</section>

<!-- RICH CONTENT SECTION -->
<section class="wrap-narrow z1" style="padding-top:8px;">

  <h2 class="sh">What is Fantasy Cricket? <small>Complete Guide</small></h2>

  <article class="prose">
    <h2>Understanding Fantasy Cricket — A Complete Beginner's Guide</h2>
    <p>Fantasy cricket is an online sports game where participants create virtual teams composed of real-life cricket players. Your virtual team earns points based on the actual statistical performance of those players in real matches — runs scored, wickets taken, catches taken, stumpings, and other contributions. The player who accumulates the most fantasy points wins the contest.</p>

    <p>In India, platforms like <strong>Dream11</strong>, MyTeam11, and MPL have transformed fantasy cricket from a niche hobby into a mainstream sport-within-a-sport, with millions of users competing across thousands of daily contests ranging from free practice games to massive paid grand leagues with crore-rupee prize pools.</p>

    <h2>How Fantasy Cricket Scoring Works</h2>
    <p>Every fantasy platform has its own scoring system, but the general principles are consistent across Dream11, MPL, and other apps. Here is how the standard Dream11 scoring system works for T20 matches:</p>

    <div class="highlight">
      <h4>📊 Standard Dream11 T20 Scoring — Key Points</h4>
      <ul>
        <li><strong>Batting:</strong> +1 point per run, +1 bonus per boundary (4s), +2 bonus per six, +8 for half-century, +16 for century, +4 for 30-run innings, -2 for a duck</li>
        <li><strong>Bowling:</strong> +25 per wicket, +8 bonus for maiden over, +4 for economy rate below 5 in T20, +8 for 3-wicket haul bonus, +16 for 5-wicket haul bonus</li>
        <li><strong>Fielding:</strong> +8 per catch, +12 per stumping, +12 per run-out (direct), +6 per run-out (indirect)</li>
        <li><strong>Captain Multiplier:</strong> Captain earns 2× all points scored — this is the single most important fantasy decision you make</li>
        <li><strong>Vice-Captain Multiplier:</strong> Vice-captain earns 1.5× all points — the second most critical pick</li>
      </ul>
    </div>

    <p>The captain and vice-captain multipliers mean that a high-scoring captain can be the difference between winning and losing a contest. A batsman who scores 80 runs (approximately 100+ fantasy points in base) becomes worth 200+ fantasy points as captain. Getting the captain right is often more valuable than getting the other 9 players right.</p>

    <h2>Why Generating Multiple Teams Maximises Your Chances</h2>
    <p>Cricket is inherently unpredictable. A batsman who averages 50 might score a duck. A bowler who rarely takes wickets might bag a five-for. <strong>No single team can account for all possible outcomes</strong>. This is why serious fantasy players — especially those targeting grand leagues — enter multiple teams.</p>

    <p>Here is the mathematical logic: if you have a 5% chance of winning a grand league with one optimised team, entering 20 diverse teams — each with different C/VC combinations and different player selections — can dramatically improve your portfolio's aggregate probability of capturing a top prize. The key word is "diverse." Simply copying the same team 20 times achieves nothing. You need <strong>genuine portfolio diversity</strong>, which is exactly what our AI generator creates.</p>

    <p>Professional fantasy players know this principle well. They call it "multi-entry strategy." Instead of putting all their hopes in one lineup, they spread their selections across multiple teams with varying captain picks, different high-risk differentials, and controlled overall player exposure — ensuring that at least one team in the portfolio fires on match day.</p>

    <h2>Captain and Vice-Captain Strategy — The Most Important Fantasy Decision</h2>
    <p>Since the captain earns 2× points and the vice-captain earns 1.5×, together they contribute roughly 45–55% of your total team score. Getting these two picks right is the single most impactful thing you can do in fantasy cricket.</p>

    <blockquote>Winning fantasy cricket isn't about picking the best 11 players — it's about picking the right captain.</blockquote>

    <h3>Safe Captain Strategy</h3>
    <p>In small leagues and head-to-head contests, the safe captain strategy works best. You pick the most consistent, in-form player who is almost certain to contribute significantly — a top-order batsman playing on a flat pitch, for example, or the primary spinner on a turning track. The risk is low and the reward is consistent.</p>

    <h3>Differential Captain Strategy</h3>
    <p>In mega grand leagues with 100,000+ entries, everyone picks the same safe captain. If your safe captain scores big, you win some points — but so does everyone else. <strong>To win a grand league, you need a captain the majority of the field doesn't have.</strong> This differential captain strategy means picking a slightly riskier choice — a middle-order finisher, a bowler, or an all-rounder — that most users ignore. When this captain fires, your team rockets up the leaderboard while others stay flat.</p>

    <h3>The 2+1 Rule for Multiple Teams</h3>
    <p>A practical framework: across your 20 teams, assign your "safe" captain to about 40% of teams, your "balanced" captain pick to 35%, and reserve 25% for a true differential. This ensures coverage if any of your three captain scenarios play out on match day.</p>

    <h2>How to Use the AI Fantasy Team Generator</h2>
    <p>Our AI team generator automates the complex work of multi-entry strategy. Here is the step-by-step process:</p>
    <ol>
      <li><strong>Select your match</strong> from the upcoming fixtures listed above, or manually input two teams.</li>
      <li><strong>Choose your mode:</strong> Safe (for H2H/small leagues), Balanced (mid-size contests), or Risky (grand leagues with 10,000+ entries).</li>
      <li><strong>Optionally configure advanced settings:</strong> Lock must-have players, exclude injury doubts, set your exposure limit (we recommend 75%), enable differential injection for late teams.</li>
      <li><strong>Click Generate AI Teams.</strong> The engine creates up to 20 unique teams in seconds.</li>
      <li><strong>Review your teams,</strong> copy them individually, or export all 20 as a PDF.</li>
      <li><strong>Enter your teams</strong> on Dream11 or your preferred platform before the deadline.</li>
    </ol>

    <div class="tips-box">
      <h4>💡 Expert Tips to Win Dream11 Grand Leagues</h4>
      <ul>
        <li><strong>Set the exposure limit to 70–80%.</strong> This ensures no single player appears in more than 75% of your 20 teams, keeping the portfolio diverse without completely excluding your strongest picks.</li>
        <li><strong>Enable differential injection</strong> for your last 10 teams. The AI will automatically favour lower-ownership players in the second half of your team set.</li>
        <li><strong>Lock 2–3 core players</strong> you are very confident about — typically a consistent all-rounder and the in-form top-order batsman — and let the AI vary the rest.</li>
        <li><strong>Use Risky mode for mega contests</strong> (50,000+ entries) and Safe mode for head-to-head or leagues under 20 people.</li>
        <li><strong>Check the weather and pitch report</strong> before generating. On slow, low pitches, weight your team toward spinners. On flat decks, prioritise explosive batsmen as captain.</li>
        <li><strong>Never use a single team in a grand league.</strong> The variance in cricket is too high. Even world-class teams get bowled out for 120 sometimes.</li>
        <li><strong>Balance your C/VC combinations.</strong> Use the "At least 5 unique C/VC combinations" setting (enabled by default) to ensure variety across your captain decisions.</li>
      </ul>
    </div>

    <h2>Safe vs Balanced vs Risky Teams — Which Mode Should You Use?</h2>

    <div class="strategy-grid">
      <div class="strategy-card strat-safe">
        <h4>🛡 Safe Mode</h4>
        <p>The AI weights low-risk players 5× above high-risk picks. Captains are selected only from the most consistent performers. Ideal for head-to-head, small leagues (2–20 entries), and situations where the loss would sting. You trade upside for consistency.</p>
      </div>
      <div class="strategy-card strat-balanced">
        <h4>⚖️ Balanced Mode</h4>
        <p>Equal weighting of low and medium risk. The AI rotates captains across multiple viable options and introduces moderate differentiation. Ideal for mid-size contests of 100–5,000 entries where you need some uniqueness but not extreme risk.</p>
      </div>
      <div class="strategy-card strat-risky">
        <h4>🔥 Risky Mode</h4>
        <p>High-risk differential players are weighted 6× above safe picks. The AI seeks out low-ownership options that could explode on match day. For IPL mega grand leagues with 50,000+ entries, this is your best shot at a life-changing finish.</p>
      </div>
    </div>

    <h2>Understanding Player Roles in Fantasy Cricket</h2>
    <p>Fantasy platforms categorise players into four roles, and each team must meet minimum and maximum quotas for each role:</p>
    <ul>
      <li><strong>Wicketkeeper (WK):</strong> 1–4 wicketkeepers per team. WKs earn extra points for stumpings and catches, making a WK who bats high in the order extremely valuable.</li>
      <li><strong>Batsman (BAT):</strong> 3–6 batsmen per team. Top-order batsmen who face the most deliveries have the highest ceiling, though middle-order finishers can surprise.</li>
      <li><strong>All-rounder (AR):</strong> 1–4 all-rounders per team. All-rounders are the most versatile assets — they can score points with both bat and ball, making them excellent captain candidates.</li>
      <li><strong>Bowler (BOWL):</strong> 3–6 bowlers per team. On good bowling surfaces, the right bowler captain choice can be the difference between a rank of 1 and rank of 1,000.</li>
    </ul>

    <h2>Fantasy Cricket for Beginners — Common Mistakes to Avoid</h2>
    <p>If you are new to fantasy cricket, here are the most common beginner mistakes and how to avoid them:</p>
    <ul>
      <li><strong>Making a single team and entering a grand league.</strong> Grand leagues require diversity. Use multiple teams.</li>
      <li><strong>Picking only star players.</strong> Everyone picks star players. Differentials — lesser-known players who could have big matches — are what separate winners from the rest of the field.</li>
      <li><strong>Ignoring the pitch and conditions.</strong> A spinner who averages 5 wickets per game on a turning pitch at home suddenly becomes a great captain choice.</li>
      <li><strong>Not checking team news.</strong> Always verify playing XI announcements before the match starts. Entering a team with a late scratch is a guaranteed loss.</li>
      <li><strong>Copying popular fantasy teams.</strong> If everyone's copying the same suggested team, everyone wins or loses together. Independent analysis and tool-generated diversity is your edge.</li>
      <li><strong>Over-managing your exposure.</strong> Setting the exposure limit too low (under 40%) leads to teams with no core — every team becomes so different they lose coherence. 65–80% is the sweet spot.</li>
    </ul>

    <h2>Frequently Asked Questions</h2>

    <div class="faq-item">
      <div class="faq-q" onclick="toggleFaq(this)">What is an AI Fantasy Cricket Team Generator? <span class="arrow">▼</span></div>
      <div class="faq-a">An AI fantasy cricket team generator uses artificial intelligence algorithms to automatically build optimised fantasy cricket teams. Our AI engine applies risk-weighted player sampling, intelligent captain rotation, role constraints (WK/BAT/AR/BOWL), and exposure controls to generate 20 unique, ready-to-enter teams for any cricket match. It removes hours of manual work and brings data-driven discipline to your fantasy portfolio.</div>
    </div>
    <div class="faq-item">
      <div class="faq-q" onclick="toggleFaq(this)">Is the AI Fantasy Team Generator completely free? <span class="arrow">▼</span></div>
      <div class="faq-a">Yes, completely free. The first 3 AI-generated teams are always immediately visible. The remaining teams unlock by watching one short 5-second simulated advertisement — no payment, subscription, registration, or account creation is ever required.</div>
    </div>
    <div class="faq-item">
      <div class="faq-q" onclick="toggleFaq(this)">Which tournaments does the generator support? <span class="arrow">▼</span></div>
      <div class="faq-a">FantasyXI AI supports all major cricket tournaments — IPL, ICC T20 World Cup, ICC ODI World Cup, ICC Champions Trophy, Big Bash League, The Hundred, SA20, ILT20, Caribbean Premier League, and all international T20 and ODI bilateral series. Use the Manual Selection tab to generate teams for any match not listed in the upcoming fixtures.</div>
    </div>
    <div class="faq-item">
      <div class="faq-q" onclick="toggleFaq(this)">How is this different from picking teams manually? <span class="arrow">▼</span></div>
      <div class="faq-a">Manual team creation for 20 unique entries would take hours and is prone to subconscious bias — you'll keep picking the same players. Our AI applies systematic probability weighting, tracks player appearances across all generated teams, enforces exposure limits, rotates C/VC combinations mathematically, and guarantees zero duplicate teams — something nearly impossible to achieve manually.</div>
    </div>
    <div class="faq-item">
      <div class="faq-q" onclick="toggleFaq(this)">What is the exposure limit setting? <span class="arrow">▼</span></div>
      <div class="faq-a">The exposure limit controls the maximum percentage of your 20 teams that any single player can appear in. At the default of 75%, no player appears in more than 15 of your 20 teams. This ensures genuine portfolio diversity — if a player has a bad game, only 75% of your teams are affected, not all 20. Lower the limit for more diversity; raise it if you want a few "core" players in almost every team.</div>
    </div>
    <div class="faq-item">
      <div class="faq-q" onclick="toggleFaq(this)">Are AI-generated teams guaranteed to win? <span class="arrow">▼</span></div>
      <div class="faq-a">No. FantasyXI AI is an informational and entertainment tool that helps you build more diverse, strategically structured fantasy portfolios. Performance in fantasy contests depends entirely on real match outcomes, which are inherently unpredictable. We strongly encourage responsible play — only enter contests you are comfortable losing.</div>
    </div>
    <div class="faq-item">
      <div class="faq-q" onclick="toggleFaq(this)">Can I export my generated teams? <span class="arrow">▼</span></div>
      <div class="faq-a">Yes. After unlocking all teams, an "Export All as PDF" button appears. This creates a clean, formatted PDF showing all 20 AI-generated teams — each with captain, vice-captain, all 11 players, their roles, and risk levels. The PDF is ideal for offline reference or printing before you enter your teams.</div>
    </div>

  </article>
</section>

</main>

""" + _FOOTER + _AD_MODAL + """
<script>
var selT1=null,selT2=null,selMID=null,selMode=null;
(function(){try{if(localStorage.getItem('fantasyxi_age_ok')==='1'){var g=document.getElementById('ageGate');if(g)g.style.display='none';}}catch(e){}})();
function ageConfirm(isAdult){
  var gate=document.getElementById('ageGate'),blocked=document.getElementById('ageBlocked');
  if(isAdult){try{localStorage.setItem('fantasyxi_age_ok','1');}catch(e){}
    if(gate){gate.style.transition='opacity .3s';gate.style.opacity='0';setTimeout(function(){gate.style.display='none';},300);}
  }else{if(gate)gate.style.display='none';if(blocked)blocked.style.display='flex';}
}
function setStep(n){for(var i=1;i<=4;i++){var el=document.getElementById('step'+i);if(!el)continue;el.classList.remove('done','active');if(i<n)el.classList.add('done');if(i===n)el.classList.add('active');}};
setStep(1);
function showTab(id,el){
  document.getElementById('tab-up').style.display=id==='up'?'':'none';
  document.getElementById('tab-man').style.display=id==='man'?'':'none';
  document.querySelectorAll('.tab-btn').forEach(function(b){b.classList.remove('active');b.setAttribute('aria-selected','false');});
  el.classList.add('active');el.setAttribute('aria-selected','true');
}
function toggleAdv(header){
  var body=document.getElementById('advBody'),arrow=header.querySelector('.adv-header-arrow');
  var isOpen=arrow.classList.contains('open');
  if(isOpen){body.style.display='none';arrow.classList.remove('open');header.setAttribute('aria-expanded','false');}
  else{body.style.display='';arrow.classList.add('open');header.setAttribute('aria-expanded','true');}
}
function selectMatch(id,t1,t2,date,venue,el){
  selMID=id;selT1=t1;selT2=t2;
  document.querySelectorAll('.match-card').forEach(function(c){c.classList.remove('selected');});
  el.classList.add('selected');
  var info=document.getElementById('selInfo');info.style.display='block';
  info.innerHTML='✅ <strong>'+t1+' vs '+t2+'</strong> · '+date+' · 📍 '+venue;
  populatePlayerChips(t1,t2);setStep(2);
  setTimeout(function(){scrollToId('section-mode');},260);
}
function setManual(){
  var t1=document.getElementById('mt1').value,t2=document.getElementById('mt2').value;
  if(t1===t2){showToast('Please select two different teams!','#ff4d6d');return;}
  selT1=t1;selT2=t2;selMID='manual';
  populatePlayerChips(t1,t2);setStep(2);showToast('✅ Teams confirmed!','#f5c842');
}
function selectMode(m,el){
  selMode=m;
  document.querySelectorAll('.mode-card').forEach(function(c){c.classList.remove('active');c.setAttribute('aria-checked','false');});
  el.classList.add('active');el.setAttribute('aria-checked','true');setStep(3);
}
var allPlayers={{ players_json|tojson }};
var lockedIds=[],excludedIds=[];
function populatePlayerChips(t1,t2){
  lockedIds=[];excludedIds=[];updateSummary('lock');updateSummary('excl');
  var teams=[{name:t1,players:(allPlayers[t1]||[]).slice(0,11)},{name:t2,players:(allPlayers[t2]||[]).slice(0,11)}];
  function buildPicker(cid,type){
    var container=document.getElementById(cid);if(!container)return;container.innerHTML='';
    teams.forEach(function(team){
      var lbl=document.createElement('div');lbl.className='chip-team-lbl';lbl.textContent=team.name;container.appendChild(lbl);
      var row=document.createElement('div');row.className='chip-row';
      (team.players||[]).forEach(function(p){
        var chip=document.createElement('button');chip.type='button';chip.className='pchip';
        chip.dataset.id=p.id;chip.dataset.name=p.name;chip.dataset.type=type;
        var rs=p.role.replace('Wicketkeeper-Batsman','WK').replace('All-rounder','AR').replace('Batsman','BAT').replace('Bowler','BOWL');
        chip.innerHTML='<span class="pchip-name">'+p.name+'</span><span class="pchip-role">'+rs+'</span>';
        chip.onclick=function(){toggleChip(chip,type);};row.appendChild(chip);
      });container.appendChild(row);
    });
  }
  buildPicker('lock_picker','lock');buildPicker('excl_picker','excl');
}
function toggleChip(chip,type){
  var id=chip.dataset.id,name=chip.dataset.name;
  var arr=(type==='lock')?lockedIds:excludedIds;
  var other=(type==='lock')?excludedIds:lockedIds;
  if(other.indexOf(id)!==-1){showToast('⚠️ '+name+' is in the other list.','#ff4d6d');return;}
  var idx=arr.indexOf(id);
  if(idx===-1){arr.push(id);chip.classList.add(type==='lock'?'pchip--active':'pchip--active-excl');}
  else{arr.splice(idx,1);chip.classList.remove('pchip--active','pchip--active-excl');}
  updateSummary(type);
}
function updateSummary(type){
  var arr=(type==='lock')?lockedIds:excludedIds;
  var el=document.getElementById(type+'_summary');if(!el)return;
  if(!arr.length){el.innerHTML='';return;}
  var cls=(type==='lock')?'pchip--active':'pchip--active-excl';
  var names=[];
  document.querySelectorAll('.pchip.'+cls+'[data-type="'+type+'"]').forEach(function(c){names.push(c.dataset.name);});
  var col=(type==='lock')?'var(--grn)':'var(--red)';
  el.innerHTML='<span style="color:'+col+';font-weight:700;">'+(type==='lock'?'🔒':'🚫')+' '+names.length+' selected: </span>'
    +'<span style="color:var(--txt2);">'+names.join(', ')+'</span>';
}
function doGenerate(){
  if(!selT1||!selT2){showToast('Please select a match first!','#ff4d6d');return;}
  if(!selMode){showToast('Please choose a generation mode!','#ff4d6d');return;}
  var cr={};
  ['c1','c6','c7','c8','c11','c12','c13','c14','c15'].forEach(function(k){var el=document.getElementById(k);cr[k]=el?el.checked:true;});
  var adv={
    unique_cap:!!(document.getElementById('unique_cap')||{}).checked,
    unique_vc:!!(document.getElementById('unique_vc')||{}).checked,
    differential:!!(document.getElementById('differential')||{}).checked,
    exposure_pct:parseInt(document.getElementById('exposure').value)||75,
    max_from_one:parseInt(document.getElementById('max_from_one').value)||7,
    risk_intensity:(parseFloat(document.getElementById('risk_intensity').value)||10)/10,
    rand_strength:(parseFloat(document.getElementById('rand_strength').value)||5)/10,
    min_diff:parseInt(document.getElementById('min_diff').value)||0,
    safe_core:false,locked:lockedIds.slice(),excluded:excludedIds.slice()
  };
  var nt=Math.min(parseInt(document.getElementById('nt').value)||20,20);
  var payload={team1:selT1,team2:selT2,match_id:selMID,mode:selMode,nt:nt,cr:cr,adv:adv};
  setStep(4);
  var spin=document.getElementById('spinnerOverlay'),btn=document.getElementById('generateBtn');
  if(spin)spin.classList.add('active');
  if(btn){btn.disabled=true;btn.style.opacity='.65';btn.textContent='Generating…';}
  var form=document.createElement('form');form.method='POST';form.action='/generate';
  var inp=document.createElement('input');inp.type='hidden';inp.name='payload';inp.value=JSON.stringify(payload);
  form.appendChild(inp);document.body.appendChild(form);setTimeout(function(){form.submit();},150);
}
function resetAll(){
  selT1=selT2=selMID=selMode=null;lockedIds=[];excludedIds=[];
  document.querySelectorAll('.match-card').forEach(function(c){c.classList.remove('selected');});
  document.querySelectorAll('.mode-card').forEach(function(c){c.classList.remove('active');c.setAttribute('aria-checked','false');});
  var info=document.getElementById('selInfo');if(info)info.style.display='none';
  ['lock_picker','excl_picker'].forEach(function(id){var el=document.getElementById(id);if(el)el.innerHTML='<span class="chip-placeholder">Select a match first</span>';});
  ['lock_summary','excl_summary'].forEach(function(id){var el=document.getElementById(id);if(el)el.innerHTML='';});
  setStep(1);showToast('🔄 Reset. Select a match to start.','#4db8ff');
  window.scrollTo({top:0,behavior:'smooth'});
}
</script>
""" + _SHARED_JS + """
</body>
</html>
"""

# =============================================================================
# ─── RESULTS PAGE ────────────────────────────────────────────────────────────
# =============================================================================

RESULTS_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<title>{{team1}} vs {{team2}} — {{teams|length}} AI Fantasy Teams | FantasyXI AI</title>
<meta name="description" content="{{teams|length}} AI-generated fantasy cricket teams for {{team1}} vs {{team2}}. {{mode|capitalize}} mode. FantasyXI AI.">
<meta name="robots" content="noindex,nofollow">
""" + _CSS + """
</head>
<body class="has-steps">
""" + _header() + """
<div class="step-bar">
  <div class="step-bar-inner">
    <div class="step done"><div class="step-num">1</div><span class="step-lbl">Match</span><div class="step-line"></div></div>
    <div class="step done"><div class="step-num">2</div><span class="step-lbl">Mode</span><div class="step-line"></div></div>
    <div class="step done"><div class="step-num">3</div><span class="step-lbl">Criteria</span><div class="step-line"></div></div>
    <div class="step active"><div class="step-num">4</div><span class="step-lbl">Generated ✓</span></div>
  </div>
</div>
<div class="success-banner z1" role="status">
  <span>✅</span>
  <div>
    <strong>{{teams|length}} AI Teams Generated!</strong>
    <span class="success-sub">First 3 are instantly free · Watch a 5-second ad to unlock all {{teams|length - 3}} remaining teams</span>
  </div>
</div>
<main class="wrap z1" id="main">
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
  <div class="stats-bar">
    <div class="stat-chip"><strong>{{teams|length}}</strong><span>Total Teams</span></div>
    <div class="stat-chip"><strong>3</strong><span>Free Preview</span></div>
    <div class="stat-chip"><strong>{{teams|length - 3}}</strong><span>Locked</span></div>
    <div class="stat-chip"><strong>{{unique_caps}}</strong><span>Captains</span></div>
    <div class="stat-chip"><strong>{{cv_combos}}</strong><span>C/VC Combos</span></div>
  </div>
  <div class="res-topbar">
    <div class="sh" style="margin-bottom:0;">Your Generated Teams</div>
    {% if unlocked %}<a href="/export_pdf" class="btn btn-grn" style="font-size:.85rem;padding:9px 18px;">📄 Export All PDF</a>{% endif %}
  </div>
  <div class="team-grid" id="mainGrid">
    {% for t in teams[:3] %}
    <div class="team-card fade-up" style="animation-delay:{{loop.index0*0.05}}s;">
      <div class="team-hdr"><div class="team-num">Team {{loop.index}}</div><span class="badge badge-free">FREE ✓</span></div>
      <div class="cv-row">
        <div class="cv-pill cv-c"><span class="cv-lbl">Captain 2×</span><span class="cv-nm">{{t.captain}}</span></div>
        <div class="cv-pill cv-vc"><span class="cv-lbl">Vice Captain 1.5×</span><span class="cv-nm">{{t.vice_captain}}</span></div>
      </div>
      <ul class="plist">{% for p in t.players %}
        <li class="pitem">
          {% if p.role=='Batsman' %}<div class="rdot d-bat"></div>{% elif p.role=='Bowler' %}<div class="rdot d-bowl"></div>{% elif p.role=='All-rounder' %}<div class="rdot d-ar"></div>{% else %}<div class="rdot d-wk"></div>{% endif %}
          <span class="pname">{{p.name}}{% if p.name==t.captain %}<span class="ct">(C)</span>{% endif %}{% if p.name==t.vice_captain %}<span class="vct">(VC)</span>{% endif %}</span>
          <span class="rtag r{{p.risk_level[0]}}">{{p.risk_level}}</span>
        </li>{% endfor %}
      </ul>
      <div class="card-foot"><div class="foot-info">{{t.from_t1}} {{team1}} · {{t.from_t2}} {{team2}}</div><button class="copy-btn" onclick="copyTeam({{loop.index0}})">📋 Copy</button></div>
    </div>{% endfor %}
    {% if not unlocked %}
    <div class="unlock-banner fade-up" id="unlockBanner" style="animation-delay:.16s;">
      <div class="unlock-count">🤖 {{teams|length - 3}} AI Teams Waiting</div>
      <h3>Unlock All {{teams|length - 3}} Remaining Teams</h3>
      <div class="unlock-perks">
        <span class="unlock-perk">✅ Completely free</span>
        <span class="unlock-perk">⏱ Takes 5 seconds</span>
        <span class="unlock-perk">📋 Copy any team</span>
        <span class="unlock-perk">📄 Export to PDF</span>
      </div>
      <p>Watch one short 5-second ad — then all teams unlock instantly.</p>
      <button class="btn btn-ora btn-xl" onclick="openAd()">▶ Watch 1 Ad → Unlock All</button>
    </div>{% endif %}
    {% for t in teams[3:] %}
    <div class="team-card fade-up" style="animation-delay:{{(loop.index+2)*0.03}}s;">
      <div class="team-hdr"><div class="team-num">Team {{loop.index+3}}</div><span class="badge badge-lock">🔒 LOCKED</span></div>
      <div class="cv-row">
        <div class="cv-pill cv-c"><span class="cv-lbl">Captain 2×</span><span class="cv-nm">{{t.captain}}</span></div>
        <div class="cv-pill cv-vc"><span class="cv-lbl">Vice Captain 1.5×</span><span class="cv-nm">{{t.vice_captain}}</span></div>
      </div>
      <ul class="plist">{% for p in t.players %}
        <li class="pitem">
          {% if p.role=='Batsman' %}<div class="rdot d-bat"></div>{% elif p.role=='Bowler' %}<div class="rdot d-bowl"></div>{% elif p.role=='All-rounder' %}<div class="rdot d-ar"></div>{% else %}<div class="rdot d-wk"></div>{% endif %}
          <span class="pname">{{p.name}}{% if p.name==t.captain %}<span class="ct">(C)</span>{% endif %}{% if p.name==t.vice_captain %}<span class="vct">(VC)</span>{% endif %}</span>
          <span class="rtag r{{p.risk_level[0]}}">{{p.risk_level}}</span>
        </li>{% endfor %}
      </ul>
      <div class="card-foot">
        <div class="foot-info">{{t.from_t1}} {{team1}} · {{t.from_t2}} {{team2}}</div>
        {% if not unlocked %}<button class="copy-btn" disabled>📋 Copy</button>
        {% else %}<button class="copy-btn" onclick="copyTeam({{loop.index+2}})">📋 Copy</button>{% endif %}
      </div>
      {% if not unlocked %}<div class="lock-ov"><div class="lock-ico">🔒</div><div class="lock-lbl">LOCKED</div><div class="lock-sub">Watch ad to unlock</div></div>{% endif %}
    </div>{% endfor %}
  </div>
  {% if unlocked %}<div style="text-align:center;margin:36px 0;"><a href="/export_pdf" class="btn btn-grn btn-xl">📄 Export All {{teams|length}} Teams as PDF</a></div>{% endif %}
  <div style="text-align:center;margin-top:22px;"><a href="/" class="btn btn-ghost">← Generate New Teams</a></div>
</main>
""" + _FOOTER + _AD_MODAL + _SHARED_JS + """
</body></html>
"""


# =============================================================================
# ─── BLOG DATA ───────────────────────────────────────────────────────────────
# =============================================================================

BLOG_POSTS = [
    {
        "slug": "how-to-win-dream11-grand-league",
        "title": "How to Win Dream11 Grand League — The Complete 2026 Strategy Guide",
        "tag": "Strategy",
        "icon": "🏆",
        "date": "March 2026",
        "read_time": "10 min read",
        "excerpt": "Grand leagues are the hardest contests in fantasy cricket — but also the most rewarding. Learn the proven portfolio strategies, differential captain picks, and multi-entry frameworks that separate consistent winners from the rest.",
        "body": """
<p>Winning a Dream11 grand league is the holy grail of fantasy cricket. With prize pools reaching crores of rupees and competition from hundreds of thousands of players, the challenge is immense — but far from impossible with the right strategy.</p>

<h2>Why Grand Leagues Are Different</h2>
<p>Before we get into strategy, you need to understand what makes grand leagues fundamentally different from small leagues and head-to-head contests. In a 10-person league, picking the 11 best players is often enough to win. In a grand league with 100,000 entries, picking the consensus "best" players guarantees a mediocre finish.</p>

<p>Here's the key insight: <strong>in grand leagues, you don't win by picking the players who score the most. You win by picking players who score more than everyone else thought they would.</strong> This is the concept of value in fantasy sports, and it's driven by ownership percentage.</p>

<blockquote>If a player is in 80% of teams and scores 100 points, you gain nothing relative to 80% of the competition. If a player is in 5% of teams and scores 80 points, you've vaulted over 95% of entries.</blockquote>

<h2>The Portfolio Approach — Why One Team Is Never Enough</h2>
<p>The most common mistake beginners make in grand leagues is entering a single team. Cricket is too unpredictable for single-entry strategy. A batsman who averages 60 can score zero on a turning pitch. A bowler who never takes five-fors can suddenly run through a batting lineup on a green seamer.</p>

<p>Professional fantasy players treat their 20 teams as a portfolio — much like a stock portfolio. Each team represents a different "bet" on how the match might unfold. Some teams bet on the aggressive opener being captain. Others back the slow-burning spinner. A few gamble on a middle-order batsman who has a history of big scores against this opposition.</p>

<p>The goal isn't to get every team into the top 10. The goal is to ensure at least one or two teams end up near the very top — and that's enough to win big prizes.</p>

<h2>Captain Selection — The Grand League Game-Changer</h2>
<p>In grand leagues, captain selection is everything. The captain earns 2× points, meaning a 150-point innings becomes 300 fantasy points. Getting the captain right when 80% of the field got it wrong is the single biggest way to win a grand league.</p>

<h3>Step 1: Identify the "safe" captain everyone will pick</h3>
<p>This is usually the most in-form batsman on the better batting team. Check Dream11 forums, social media, and expert predictions — whoever appears most often is the "consensus" captain. Make a note of this player's expected ownership (typically 40–65% in high-entry contests).</p>

<h3>Step 2: Find your differentials</h3>
<p>A differential captain is someone with lower public ownership (ideally under 15%) but realistic potential to be the highest scorer. Look for:</p>
<ul>
  <li>Middle-order batsmen with history of big innings against this opposition</li>
  <li>All-rounders who have been in excellent recent form with both bat and ball</li>
  <li>Bowlers on pitches heavily favouring their style (spinners on dry pitches, pacers on green tops)</li>
  <li>Players who historically excel at this specific venue</li>
</ul>

<h3>Step 3: Distribute your captain picks across teams</h3>
<p>A sound distribution across 20 teams might look like this: 8 teams with the consensus captain, 6 with your primary differential, and 6 split across two or three secondary differentials. This way, whichever captain scenario plays out, you have meaningful coverage.</p>

<h2>Building Genuine Team Diversity</h2>
<p>Diversity isn't just about changing the captain. Every position in your team matters for grand league uniqueness.</p>

<p>For core players (players you're very confident about), set the exposure limit at 80–90% — they appear in most but not all your teams. For your differential bets, keep exposure at 20–40% so they only appear in a handful of teams. This way, when differentials fire, only some of your teams benefit (but those teams rocket up the leaderboard).</p>

<h2>Using FantasyXI AI for Grand League Entries</h2>
<p>Our AI generator is built specifically for the grand league multi-entry strategy. Select <strong>Risky mode</strong> for grand leagues. This weights high-risk differential players much more heavily, creating the kind of unique combinations that separate your portfolio from the crowd.</p>

<p>Enable <strong>Differential Injection</strong> — this ensures your last 10 teams automatically include low-ownership players who most users will ignore. Enable <strong>Unique Captain per Team</strong> to spread your captain picks across as many different options as possible.</p>

<div class="highlight">
  <h4>🏆 Grand League Checklist</h4>
  <ul>
    <li>✅ Check pitch report and weather — conditions drive everything</li>
    <li>✅ Verify playing XI is announced before entering</li>
    <li>✅ Generate 20 teams in Risky mode with differential injection</li>
    <li>✅ Identify 2–3 captain candidates with different ownership profiles</li>
    <li>✅ Set exposure limit at 70–80% for core players</li>
    <li>✅ Keep at least 5 truly differential teams per 20-team set</li>
    <li>✅ Never enter the exact same team twice</li>
    <li>✅ Play responsibly — only spend what you can afford to lose</li>
  </ul>
</div>

<h2>Match Reading — The Edge Most Fantasay Players Don't Use</h2>
<p>AI tools give you structural diversity. Match reading gives you the directional edge. Before generating your teams, spend 15 minutes on these factors:</p>

<p><strong>Pitch and venue history:</strong> Some venues are batting paradises (Wankhede, Chinnaswamy). Others are graveyard for batsmen (Eden Gardens early in the season). Research the last 5–8 T20 matches at the venue and calculate the average first innings score.</p>

<p><strong>Toss and batting order:</strong> On tracks where dew plays a role, chasing teams often have a massive advantage. If your team is likely to bat second, their top-order batsmen become even more valuable as they'll be batting in better conditions.</p>

<p><strong>Head-to-head records:</strong> Some bowlers have a psychological edge over certain batsmen. Certain batsmen average significantly higher against pace vs spin. These matchups can guide both player selection and captain choice.</p>

<h2>Bankroll Management — Play Smart, Play Long</h2>
<p>The final piece of grand league strategy is bankroll management. Even the best fantasy players don't win every contest. Over a long enough sample, good strategy wins out — but the short-term variance is brutal.</p>

<p>Never spend more than 5–10% of your fantasy bankroll on any single match. If you have ₹1,000 to spend on fantasy cricket this month, cap your spending at ₹100–150 per match day. This gives you enough shots across multiple matches to let your strategy work.</p>

<p>Fantasy cricket is a long game. The players who win consistently aren't the luckiest — they're the most disciplined. They build diverse portfolios, they do their research, they manage their bankroll, and they play match after match, letting their edge accumulate over time.</p>

<div class="warn-box">
  <h4>⚠️ Responsible Play</h4>
  <p>Fantasy sports involve real financial risk. Always play within your means. Set a monthly budget and stick to it. If you find yourself chasing losses, take a break. Fantasy cricket should be fun — treat it as entertainment, not income.</p>
</div>
"""
    },
    {
        "slug": "fantasy-cricket-beginners-guide",
        "title": "Fantasy Cricket Beginner's Guide — Everything You Need to Know in 2026",
        "tag": "Beginners",
        "icon": "📖",
        "date": "March 2026",
        "read_time": "8 min read",
        "excerpt": "New to fantasy cricket? This complete beginner's guide covers how fantasy cricket works, how scoring works, which platform to choose, and step-by-step instructions to create your first winning team.",
        "body": """
<p>Fantasy cricket has exploded in India over the last decade, transforming from a niche hobby into a mainstream phenomenon with over 150 million registered users across platforms like Dream11. If you're new to the game, this guide will walk you through everything you need to know — from the basics of how it works to your first winning team strategy.</p>

<h2>What is Fantasy Cricket?</h2>
<p>Fantasy cricket is an online game where you create a virtual team of real cricket players. Your team earns points based on how those players perform in actual matches. The better your players perform in real life, the more points your fantasy team scores. Players with the most points at the end of the match win prizes.</p>

<p>You're not betting on match outcomes — you're betting on individual player performances. A match can end in a draw but your fantasy team can still finish first if your selected players scored most of the runs and took most of the wickets.</p>

<h2>How Does a Fantasy Team Work?</h2>
<p>On Dream11 (India's most popular platform), every fantasy team consists of exactly 11 players selected from the two real teams playing the match. There are rules about how many players you can pick from each team and what roles they must play:</p>
<ul>
  <li><strong>Wicketkeeper (WK):</strong> 1 to 4 players</li>
  <li><strong>Batsmen (BAT):</strong> 3 to 6 players</li>
  <li><strong>All-rounders (AR):</strong> 1 to 4 players</li>
  <li><strong>Bowlers (BOWL):</strong> 3 to 6 players</li>
  <li>Maximum 7 players from one team</li>
</ul>

<p>Once you've picked your 11 players, you select one as <strong>Captain</strong> (earns 2× points) and one as <strong>Vice-Captain</strong> (earns 1.5× points). These two picks are the most important decisions in fantasy cricket.</p>

<h2>How is Fantasy Cricket Scored?</h2>
<p>Points are awarded for real match contributions. The exact scoring varies by platform and format (T20, ODI, Test), but here's the general Dream11 T20 scoring system:</p>

<div class="highlight">
  <h4>📊 Dream11 T20 Points System</h4>
  <ul>
    <li>Every run scored: +1 point</li>
    <li>Every four hit: +1 bonus</li>
    <li>Every six hit: +2 bonus</li>
    <li>Half-century (50 runs): +8 bonus</li>
    <li>Century (100 runs): +16 bonus</li>
    <li>Duck (0 runs, batting): -2 points</li>
    <li>Every wicket taken: +25 points</li>
    <li>Every maiden over (T20): +8 bonus</li>
    <li>3-wicket haul bonus: +4 points</li>
    <li>5-wicket haul bonus: +16 points</li>
    <li>Every catch: +8 points</li>
    <li>Every stumping: +12 points</li>
    <li>Run out (direct): +12 points</li>
  </ul>
</div>

<h2>Choosing the Right Contest</h2>
<p>Dream11 offers several types of contests. As a beginner, start with these:</p>

<p><strong>Practice Contests (Free):</strong> These are completely free to enter and a great way to learn without risking money. Your team earns points exactly like paid contests, but prizes are small or non-existent.</p>

<p><strong>Small Leagues (2–20 players, ₹10–₹50 entry):</strong> These are the best starting point for paid play. With fewer players in the contest, your chances are much higher than grand leagues. The prizes are smaller, but so is the competition.</p>

<p><strong>Head-to-Head (2 players):</strong> Just you vs. one opponent. The player with more points wins. Perfect for beginners because there are only two outcomes.</p>

<p><strong>Grand Leagues (50,000+ players, ₹5–₹49 entry):</strong> The biggest prizes but lowest win probability. Only enter grand leagues once you've gained experience. Never put all your budget into grand leagues as a beginner.</p>

<h2>Creating Your First Fantasy Team — Step by Step</h2>
<p>Here's a practical guide to creating your first team for any T20 match:</p>

<p><strong>Step 1 — Research the match.</strong> Find out which players are confirmed in the playing XI. Check recent form (last 5 matches), pitch conditions, and weather. This takes about 10–15 minutes but dramatically improves your picks.</p>

<p><strong>Step 2 — Pick your core players.</strong> Start with 2–3 players you're very confident about — typically the consistent run-scorer in the top order and the main strike bowler. These are your "safe" picks.</p>

<p><strong>Step 3 — Add value picks.</strong> Fill the rest of your team with players who have upside. All-rounders who contribute with both bat and ball are excellent value. An in-form wicketkeeper who bats at No. 4 offers runs, catches, and stumping points.</p>

<p><strong>Step 4 — Choose your captain carefully.</strong> For your first teams, choose someone who is almost certain to contribute significantly — the team's leading run-scorer or wicket-taker. As you gain experience, you can experiment with more creative captain choices.</p>

<p><strong>Step 5 — Use our AI generator.</strong> Instead of manually creating 20 teams, use FantasyXI AI to generate a diverse set of lineups in seconds. Even as a beginner, entering multiple teams (even at small stakes) gives you a much better experience of how fantasy cricket works.</p>

<h2>Common Beginner Mistakes</h2>
<p>Everyone makes mistakes when starting out. Here's how to avoid the most common ones:</p>

<p><strong>Picking players based on reputation, not form.</strong> A legendary batsman who scored 12 runs in his last 5 matches is a poor fantasy pick regardless of his career average. Recency matters enormously in fantasy cricket.</p>

<p><strong>Ignoring the pitch and venue.</strong> A slow, spinning Chepauk pitch makes spinners gold. The same spinners on a Wankhede flat track might be expensive. Always factor in conditions.</p>

<p><strong>Not checking the playing XI.</strong> Players who are rested, injured, or dropped don't earn points. Always verify the confirmed playing XI — usually announced 30–60 minutes before match start — before entering your teams.</p>

<p><strong>Entering a grand league with a single team as your first paid contest.</strong> The odds of winning a grand league on your first attempt are extremely low. Build experience with free contests and small leagues first.</p>

<h2>Key Terms Every Fantasy Cricket Player Should Know</h2>
<p><strong>Differential:</strong> A low-ownership player who could outscore popular picks. Differentials are essential for grand league wins.</p>
<p><strong>Exposure:</strong> The percentage of your teams a player appears in. High exposure means that player dominates your portfolio — great if they perform, disastrous if they don't.</p>
<p><strong>Ownership percentage:</strong> How many fantasy entries (as a percentage) have selected a particular player. High ownership = safe but low ceiling. Low ownership = risky but high reward.</p>
<p><strong>C/VC combination:</strong> Your captain and vice-captain pair. Different C/VC combos across 20 teams are the core of multi-entry grand league strategy.</p>
<p><strong>Playing XI:</strong> The 11 players actually confirmed to play in the match. Always wait for this confirmation before finalising your teams.</p>

<div class="tips-box">
  <h4>💡 Beginner Quick Tips</h4>
  <ul>
    <li>Start with free practice contests to learn without risk</li>
    <li>Pick all-rounders — they earn points with both bat and ball</li>
    <li>Always check the playing XI before submitting</li>
    <li>Small leagues (2–20 players) are better than grand leagues for beginners</li>
    <li>Use FantasyXI AI to generate multiple teams automatically</li>
    <li>Set a strict monthly budget and never exceed it</li>
    <li>Track your results — learn which strategies work best for you</li>
  </ul>
</div>
"""
    },
    {
        "slug": "best-captain-vc-combinations",
        "title": "Best Captain & Vice-Captain Combinations for Fantasy Cricket — 2026 Guide",
        "tag": "Captain Strategy",
        "icon": "👑",
        "date": "March 2026",
        "read_time": "9 min read",
        "excerpt": "The captain earns 2× points and the vice-captain 1.5×. Together they drive 45–55% of your total fantasy score. Master the art of C/VC selection with this comprehensive guide to the best combinations for every match scenario.",
        "body": """
<p>If there's one skill that separates consistent fantasy cricket winners from the rest, it's captain and vice-captain selection. Together, the captain (2× multiplier) and vice-captain (1.5× multiplier) contribute roughly 45–55% of your total fantasy team score. Get both right and you're in contention. Get both wrong and even a perfect remaining 9 players can't save you.</p>

<h2>Why Captain Selection is the Most Important Fantasy Decision</h2>
<p>Let's look at the mathematics. In a typical high-scoring T20 match, the winning fantasy team scores around 500–600 points. The captain alone accounts for approximately 150–200 of those points. A batsman who scores 80 runs (roughly 90–100 base fantasy points) becomes 180–200 points as captain.</p>

<p>Now consider the vice-captain. That same player at 1.5× multiplier contributes 135–150 points vs. 90–100 without the multiplier. The combined "bonus" from C/VC picks over making them regular players is roughly 100–150 extra points — the equivalent of a bonus batsman who scores 70 runs without facing a single delivery.</p>

<h2>Types of Captain Picks — Safe, Balanced, and Differential</h2>

<h3>The Safe Captain (for small leagues and H2H)</h3>
<p>In small leagues and head-to-head contests, the safe captain strategy works best. A safe captain is someone with the highest floor — the most likely to score significant points even if their performance is slightly below their peak.</p>

<p>Characteristics of a good safe captain:</p>
<ul>
  <li>Consistent performer over the last 10 matches</li>
  <li>Bats/bowls in a position that guarantees impact (top-order batsman, main strike bowler)</li>
  <li>Has a strong recent record at this specific venue</li>
  <li>Good head-to-head record against this specific opposition</li>
  <li>Not injury-prone or likely to be rotated</li>
</ul>

<h3>The Balanced Captain (for mid-size contests)</h3>
<p>For contests of 100–10,000 entries, the balanced captain picks up where the safe captain leaves off. You still want a reliable performer, but you're looking for someone with slightly lower ownership — say 20–35% — who still has a very high ceiling.</p>

<p>All-rounders make excellent balanced captain picks. They have two ways to score big: a batting performance AND a bowling performance. A player who takes 2 wickets and scores 40 runs provides roughly 110–120 base points — 220–240 as captain. This dual-threat potential is unique to all-rounders and makes them perennially undervalued as captain choices.</p>

<h3>The Differential Captain (for grand leagues)</h3>
<p>This is the grand league gamble. A differential captain has low public ownership (under 10–15%) but realistic potential to top-score. The logic: if your differential captain has a big game, most of the 100,000+ entries in the contest don't have them as captain. You leapfrog them all in one move.</p>

<p>The best differential captain scenarios:</p>
<ul>
  <li>A middle-order batsman promoted up the batting order</li>
  <li>A bowler on a pitch perfectly suited to his style</li>
  <li>A player returning from injury or a long rest who tends to hit big on return</li>
  <li>An overseas player who has a historic record against this specific opposition</li>
</ul>

<h2>The Best C/VC Combinations by Match Scenario</h2>

<div class="highlight">
  <h4>📋 C/VC Framework by Contest Type</h4>
  <ul>
    <li><strong>Head-to-Head:</strong> Safe BAT captain + All-rounder VC. Maximise consistency.</li>
    <li><strong>Small League (under 50 entries):</strong> Safe/Balanced captain + reliable all-rounder VC. Balance upside with floor.</li>
    <li><strong>Mid Contest (50–5,000 entries):</strong> Balanced captain + differential VC. Some creativity needed.</li>
    <li><strong>Large Contest (5,000–50,000 entries):</strong> Balanced captain + aggressive differential VC. Higher risk, higher ceiling.</li>
    <li><strong>Mega Grand League (50,000+ entries):</strong> Differential captain + aggressive differential VC across multiple teams. Only route to the top.</li>
  </ul>
</div>

<h2>The Role of All-Rounders in C/VC Strategy</h2>
<p>All-rounders deserve a dedicated section in any C/VC guide. The best all-rounders in world cricket — players who bat in the top 6 AND regularly take wickets — are the most valuable fantasy assets available. They have two scoring engines running simultaneously.</p>

<p>When selecting your captain from all-rounders, look for:</p>
<ul>
  <li>Batting position: ideally No. 4–6 (enough deliveries to score significantly)</li>
  <li>Bowling role: main strike bowler or at minimum completes full allocation of overs</li>
  <li>Recent form with both bat and ball (not just one discipline)</li>
  <li>Match context: all-rounders are especially valuable in matches expected to be close, where the team batting second's middle-order will be tested</li>
</ul>

<h2>Vice-Captain Strategy — Don't Just Pick Your Second-Best Player</h2>
<p>Most fantasy players pick the captain they're most confident about, then pick their second-favourite player as vice-captain. This is sub-optimal. Here's a better framework:</p>

<p><strong>Complement your captain pick.</strong> If your captain is a top-order batsman, pick an all-rounder or bowler as vice-captain. This gives you diversified scoring streams — if the pitch is bowling-friendly and batting underperforms, at least your VC earns big.</p>

<p><strong>In multi-team strategies, vary your VC across teams.</strong> Having the same captain and vice-captain in all 20 teams means you have exactly the same upside exposure as someone who entered one team. The FantasyXI AI generator enforces at least 5 unique C/VC combinations across your 20 teams by default.</p>

<h2>Reading the Pitch and Conditions for C/VC Selection</h2>
<p>Conditions heavily influence which player profile is most likely to score big:</p>

<p><strong>Batting-friendly flat tracks (typical IPL venues like Wankhede, Chinnaswamy):</strong> Prioritise top-order batsmen and power-hitters. A batsman who makes 80–100 runs on a flat deck is a common outcome. C/VC from batsmen makes sense.</p>

<p><strong>Slow, turning pitches (Chepauk, Eden Gardens early season):</strong> Spinners who take 3–4 wickets in a T20 become extraordinary fantasy assets. Consider your primary spinner as captain — many users will ignore this choice, giving you a differential edge.</p>

<p><strong>Seam-friendly green tops (in England, New Zealand, early season India):</strong> Fast bowlers who take 3–5 wickets with tight economy become ideal captain choices. Watch the toss — teams bowling first on a green top have massive advantage.</p>

<div class="tips-box">
  <h4>💡 C/VC Quick Decision Framework</h4>
  <ul>
    <li>Check pitch report and recent scores at this venue</li>
    <li>Identify the 3 players most likely to be the match's highest fantasy scorer</li>
    <li>Check ownership estimates — avoid captains with 60%+ ownership in grand leagues</li>
    <li>Assign your safest pick as captain in H2H/small league teams</li>
    <li>Assign 1–2 differentials as captain in your grand league teams</li>
    <li>Never make the same C/VC pair in all 20 teams</li>
    <li>Consider all-rounders as vice-captain — they're often undervalued and high-ceiling</li>
  </ul>
</div>
"""
    },
    {
        "slug": "safe-vs-risky-fantasy-teams",
        "title": "Safe vs Risky Fantasy Teams — Which Strategy Should You Use?",
        "tag": "Strategy",
        "icon": "⚖️",
        "date": "February 2026",
        "read_time": "7 min read",
        "excerpt": "Safe teams win small leagues consistently. Risky teams win grand leagues occasionally but spectacularly. Understanding when to be safe and when to take risks is the foundation of a long-term profitable fantasy cricket strategy.",
        "body": """
<p>One of the most fundamental questions every fantasy cricket player faces before entering a contest is this: should I go safe or take risks? The answer isn't simple — it depends on the type of contest, the size of the prize pool, and your personal risk tolerance. This guide breaks down both strategies comprehensively so you can make an informed decision for every match.</p>

<h2>Defining "Safe" and "Risky" in Fantasy Cricket</h2>
<p>A <strong>safe fantasy team</strong> prioritises consistency over upside. It selects players who are almost certain to contribute — in-form top-order batsmen, the team's primary wicket-taker, the wicketkeeper who bats high. These players rarely score zero. They might not top-score either, but they're reliably in the 40–80 base point range.</p>

<p>A <strong>risky fantasy team</strong> prioritises ceiling over floor. It deliberately includes players who might score 10 points or 150 points depending on the day — lower-order hitters who occasionally explode, young pace bowlers on seaming pitches, middle-order batsmen who can hit a century or bat at No. 8.</p>

<p>Neither approach is universally better. The optimal choice depends entirely on the contest you're entering.</p>

<h2>When to Choose a Safe Strategy</h2>

<h3>Head-to-Head Contests</h3>
<p>In a direct 1v1 battle, consistency beats variance. You need to outscore one specific person. There's no value in having an explosive team that sometimes scores 700 points and sometimes scores 250 — because in the 250-point games, you lose. A safe team that consistently delivers 450–500 points will win more H2H contests over time than a risky team with high variance.</p>

<h3>Small Private Leagues (Friends and Family)</h3>
<p>When you're in a small league of 5–20 people, the dynamics are similar to H2H. You're competing against a known field, and the field is likely picking popular, safe players too. Beating them requires either being consistently correct (safe strategy) or getting a few massive performances. In small leagues, the safe route is almost always optimal.</p>

<h3>When You're Not Sure About the Match</h3>
<p>If you haven't had time to do proper research on the pitch, team news, and form, defaulting to the safe strategy protects you. The safe picks — top-order batsmen in form, main wicket-taker, reliable all-rounder — are safe precisely because they're almost always in good positions to score regardless of match conditions.</p>

<h2>When to Choose a Risky Strategy</h2>

<h3>Grand Leagues (10,000+ entries)</h3>
<p>This is the single most important context for risky strategy. In a grand league, everyone picks the same safe captain. Everyone avoids the unpredictable middle-order hitter. Everyone goes with the in-form opener. The result: the safe team is in 70% of entries, and your first-place finish requires beating 70% of the field with the same players — which means you win when your captain moderately outperforms everyone else's, but the upside is limited.</p>

<p>The risky team's logic: if your differential captain has a 20% chance of being the highest scorer in the match, and only 5% of entries have them as captain, then when they fire, you leapfrog 95% of entries in one shot. Over 10 grand league entries with risky strategy, you might win nothing in 8 of them but place in the top 3 twice — and those two wins are life-changing.</p>

<h3>When You Have Strong Conviction About a Differential</h3>
<p>Sometimes you identify a player who the market is significantly undervaluing. Maybe a bowler playing his first match in months on a surface perfectly suited to him. Maybe a batting allrounder who is batting up the order this week due to a top-order injury. When you have genuine conviction on a differential — backed by research — the risky strategy unlocks the corresponding reward.</p>

<h2>The FantasyXI AI Approach — Three Modes</h2>
<p>Our AI generator translates this strategy framework into three concrete modes:</p>

<div class="strategy-grid">
  <div class="strategy-card strat-safe">
    <h4>🛡 Safe Mode</h4>
    <p>Low-risk players weighted 5× higher. Captain pool restricted to the most consistent performers. Ideal for H2H and small leagues. Maximises your average score at the cost of explosive potential.</p>
  </div>
  <div class="strategy-card strat-balanced">
    <h4>⚖️ Balanced Mode</h4>
    <p>Equal weighting of low and medium risk. Smart C/VC rotation across multiple viable options. Best for mid-size contests of 50–5,000 entries. Good average with moderate upside.</p>
  </div>
  <div class="strategy-card strat-risky">
    <h4>🔥 Risky Mode</h4>
    <p>High-risk players weighted 6× higher. Differential captain injection. Maximum portfolio diversity. For IPL mega grand leagues only. High variance but highest ceiling.</p>
  </div>
</div>

<h2>Mixing Safe and Risky — The Portfolio Blend</h2>
<p>The smartest approach for serious players entering 20 teams is not pure safe or pure risky — it's a deliberate blend. Here's a recommended portfolio structure for 20 teams entered across different contest types:</p>
<ul>
  <li><strong>4 teams in Safe mode</strong> — entered into H2H and small leagues for consistent returns</li>
  <li><strong>8 teams in Balanced mode</strong> — entered into medium contests for balanced risk/reward</li>
  <li><strong>8 teams in Risky mode</strong> — entered into grand leagues chasing the big prize</li>
</ul>

<p>This structure means you're never going all-in on variance (which can be devastating on bad days) but you're always taking meaningful shots at the high-value grand league prizes.</p>

<h2>Risk Management — The Often-Ignored Side of Fantasy Strategy</h2>
<p>Choosing between safe and risky teams is ultimately a risk management decision. Here are some principles to guide it:</p>

<p><strong>Stake risk vs. team risk.</strong> You can play a risky team at a low stake (₹11 entry) or a safe team at a high stake (₹1,100 entry). These are separate decisions. Don't confuse them. A risky team at a low stake is far safer than a safe team at a high stake.</p>

<p><strong>Track your results.</strong> Over 20–30 matches, you'll have data on whether safe or risky strategy is working better for you. Fantasy cricket requires iteration — adjust your approach based on real results, not intuition.</p>

<p><strong>Never enter a contest you can't afford to lose.</strong> This applies to all fantasy sports. Set a budget at the start of the month and treat it as entertainment spending. The moment you're chasing losses is the moment the fun ends and the problems begin.</p>

<div class="warn-box">
  <h4>⚠️ Important Disclaimer</h4>
  <p>Fantasy cricket involves financial risk. Neither safe nor risky strategies guarantee winnings. FantasyXI AI is an informational tool — we help you build diverse, strategic teams, but we cannot control match outcomes. Always play responsibly, within your means, and for fun first.</p>
</div>
"""
    },
    {
        "slug": "fantasy-cricket-winning-strategies",
        "title": "Fantasy Cricket Winning Strategies — 15 Proven Tips for 2026",
        "tag": "Strategy",
        "icon": "🎯",
        "date": "February 2026",
        "read_time": "11 min read",
        "excerpt": "From pitch reading and ownership analysis to multi-entry portfolio construction and bankroll management — 15 proven fantasy cricket strategies that professional players use to win consistently across IPL, Dream11, and all major platforms.",
        "body": """
<p>Winning at fantasy cricket consistently requires more than luck. The players who finish in the top percentiles of grand leagues — match after match, season after season — do so through systematic strategy, disciplined research, and smart portfolio management. Here are 15 proven strategies used by professional fantasy cricket players.</p>

<h2>Strategy 1: Always Verify the Playing XI Before Submitting</h2>
<p>This sounds obvious, but it's the most common mistake that costs fantasy players money. Team announcements usually come 30–60 minutes before a match. A player who is named in the playing XI earns points. A rested, injured, or dropped player earns zero. Entering a team with a player who doesn't play is the most avoidable way to lose.</p>
<p>Set a reminder 45 minutes before every match. Check official team social media accounts and news apps for the confirmed XI. Only then submit your teams.</p>

<h2>Strategy 2: Research Pitch and Venue Conditions</h2>
<p>Cricket is uniquely dependent on conditions. A spinner who averages 18 wickets per season on home turning tracks might average 6 on pace-friendly pitches. Before every match, find out the last 8–10 T20 scores at this venue. Calculate the average first-innings score. Understand whether the pitch favours batsmen or bowlers — and build your team accordingly.</p>

<h2>Strategy 3: Use the Weather Forecast</h2>
<p>Dew, rain interruptions, and overcast conditions all dramatically affect match dynamics. Overcast conditions help swing bowlers — prioritise pace. Heavy dew in the second innings makes chasing much easier — the team batting second benefits. Use a reliable weather app for the match venue and factor it into your captain selection especially.</p>

<h2>Strategy 4: Understand Ownership Percentages</h2>
<p>In grand leagues, ownership percentage is as important as player quality. A player owned by 70% of entries who scores 100 points gets you nowhere in the leaderboard — everyone else benefits equally. A player owned by 8% who scores 80 points rockets you past 92% of the field. Track expected ownership before selecting your captain and key differentials.</p>

<h2>Strategy 5: Prioritise All-Rounders</h2>
<p>All-rounders have two scoring engines. They earn points with both bat and ball. An all-rounder who scores 40 runs AND takes 2 wickets contributes roughly 100 base points — almost the same as a batsman who scores 80 runs. For the same fantasy "cost," all-rounders provide better expected value in nearly every match.</p>

<h2>Strategy 6: Build a Balanced Core with a Few Differentials</h2>
<p>The optimal team structure is 6–7 "core" picks (players you're very confident about) and 4–5 "differential" picks (lower-ownership players with high upside). This gives you a solid floor while retaining meaningful chances at a grand league finish when your differentials fire.</p>

<h2>Strategy 7: Use Multiple Teams — Even at Small Stakes</h2>
<p>The variance in cricket is too high for single-entry strategy. Entering 5–10 teams in a mid-size contest at ₹22 each is often better than one team at ₹110. You get 5–10 different captain/VC combinations and lineup variations. When cricket goes unpredictably — and it always does — at least one of your teams has the right players.</p>

<h2>Strategy 8: Rotate Captains Systematically</h2>
<p>Across your 20 AI-generated teams, you should have at least 3–5 different captain picks. The FantasyXI AI default settings enforce this. In the real world, pick 2–3 captain candidates before generating teams: your "safe" captain (high probability, high ownership), your "balanced" captain (moderate ownership, high ceiling), and your "differential" captain (low ownership, high upside).</p>

<h2>Strategy 9: Lock Your Highest-Conviction Players</h2>
<p>Use the AI generator's "Lock Players" feature for 2–3 players you're extremely confident about. If a top-order batsman has been averaging 65 in the last 5 matches and is playing on his home ground with a batting-friendly pitch, lock him into every team. Let the AI vary the rest while guaranteeing your core conviction is always included.</p>

<h2>Strategy 10: Exclude Injury Doubts and Low-Confidence Picks</h2>
<p>Just as important as locking is excluding. If a player is nursing a hamstring injury, hasn't confirmed in the playing XI, or has performed poorly in the last 6 matches without excuse, use the "Exclude Players" feature. Remove them from consideration entirely and let the AI fill that spot with alternatives.</p>

<h2>Strategy 11: Study Head-to-Head Records</h2>
<p>Some players have remarkable records against specific opponents. A spinner who dismisses a certain batsman 6 times in 8 career encounters has a psychological and statistical edge in that matchup. Research head-to-head records using cricinfo or ESPN Cricinfo — it's publicly available and most casual players ignore it.</p>

<h2>Strategy 12: Exploit Toss and Batting Order Decisions</h2>
<p>In dew-affected matches or on pitches that deteriorate quickly, the toss winner (especially if they opt to chase) has a significant match advantage. Players from the team batting second often have a higher scoring ceiling in these conditions. Adjust your team composition slightly after the toss if matches permit.</p>

<h2>Strategy 13: Track Recent Form Over Career Statistics</h2>
<p>Fantasy cricket is about predicting what a player will do in the NEXT match, not what they've done over their career. A player averaging 40 over 10 years who has scored 8, 12, 15, 4, and 9 in their last 5 innings is in terrible form. A young player averaging 22 who has scored 45, 38, 52, 40, and 47 recently is in exceptional form. Weight recent performance far more heavily than career statistics.</p>

<h2>Strategy 14: Manage Your Fantasy Bankroll</h2>
<p>Set a monthly fantasy budget. Divide it across the matches you plan to enter. Never bet more than 5% of your monthly bankroll on any single match day. This ensures you stay in the game long enough for your strategy to compound across many matches. The players who go all-in on one match and lose everything never get to develop as fantasy players.</p>

<h2>Strategy 15: Review and Iterate Every Match</h2>
<p>After every match, review your teams. Which picks worked? Which ones failed and why? Was it a research error (you should have known), a condition change (weather, pitch played differently than expected), or pure variance (the player just had a bad day despite perfect selection)? Track your decision quality, not just results. Good decisions that lead to bad outcomes (because of variance) are still good decisions. Bad decisions that lead to good outcomes are still bad decisions — and you'll pay for them eventually.</p>

<div class="tips-box">
  <h4>💡 The One-Sentence Summary</h4>
  <ul>
    <li>Always check the playing XI. Always read the pitch. Always vary your C/VC combinations. Always manage your bankroll. And always remember that fantasy cricket is entertainment first.</li>
  </ul>
</div>
"""
    },
]

# Build slug lookup
BLOG_INDEX = {p["slug"]: p for p in BLOG_POSTS}


# =============================================================================
# ─── PAGE TEMPLATES ──────────────────────────────────────────────────────────
# =============================================================================

def page_shell(title, meta_desc, canonical, active, content, body_class="no-steps"):
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<title>{title} | FantasyXI AI</title>
<meta name="description" content="{meta_desc}">
<meta name="robots" content="index,follow">
<meta property="og:title" content="{title}">
<meta property="og:description" content="{meta_desc}">
<meta property="og:type" content="website">
<link rel="canonical" href="https://fantasyxi.in{canonical}">
{_CSS}
</head>
<body class="{body_class}">
{_header(active)}
<main id="main">
{content}
</main>
{_FOOTER}
<div class="toast" id="toast" role="status" aria-live="polite"></div>
<script>function showToast(msg,col){{var t=document.getElementById('toast');if(!t)return;t.textContent=msg;t.style.background=col||'#00e5a0';t.style.color='#000';t.classList.add('show');setTimeout(function(){{t.classList.remove('show');}},3000);}}
function toggleFaq(el){{var a=el.nextElementSibling;var isOpen=el.classList.contains('open');document.querySelectorAll('.faq-q').forEach(function(q){{q.classList.remove('open');if(q.nextElementSibling)q.nextElementSibling.classList.remove('open');}});if(!isOpen){{el.classList.add('open');if(a)a.classList.add('open');}}}}</script>
</body>
</html>"""


def guide_content():
    return """
<section class="wrap-narrow">
  <div class="blog-article-header">
    <span class="blog-tag">📖 Complete Guide</span>
    <h1>Fantasy Cricket Guide — Everything You Need to Know</h1>
    <div class="meta"><span>📅 Updated March 2026</span><span>⏱ 12 min read</span><span>👤 FantasyXI Team</span></div>
  </div>
  <article class="prose">
    <h2>What is Fantasy Cricket?</h2>
    <p>Fantasy cricket is an online strategy game where you build a virtual team of real cricket players and earn points based on their actual match-day performance. Unlike match betting (which is based on team outcomes), fantasy cricket rewards individual player performance — runs scored, wickets taken, catches, and other statistical contributions.</p>
    <p>India has become the global capital of fantasy cricket, with over 150 million registered users across platforms like Dream11, MyTeam11, and MPL. Contests range from free practice games to grand leagues with crore-rupee prize pools.</p>

    <h2>How Fantasy Cricket Scoring Works</h2>
    <p>Points are earned (and sometimes lost) based on real match statistics. The exact system varies by platform and format, but here are the key components in Dream11's T20 scoring system:</p>
    <div class="highlight">
      <h4>📊 Dream11 T20 Scoring — Key Rules</h4>
      <ul>
        <li><strong>Batting:</strong> +1 per run, +1 per boundary, +2 per six, +8 for fifty, +16 for century, -2 for duck</li>
        <li><strong>Bowling:</strong> +25 per wicket, +8 for maiden, bonus points for 3WK haul (+8) and 5WK haul (+16)</li>
        <li><strong>Fielding:</strong> +8 per catch, +12 per stumping, +12 for direct run-out, +6 indirect</li>
        <li><strong>Captain:</strong> 2× ALL points earned</li>
        <li><strong>Vice-Captain:</strong> 1.5× ALL points earned</li>
      </ul>
    </div>

    <h2>Team Composition Rules</h2>
    <p>Every fantasy team must have exactly 11 players from the two sides playing the match. Composition requirements on Dream11:</p>
    <ul>
      <li>1–4 Wicketkeeper-Batsmen</li>
      <li>3–6 Batsmen</li>
      <li>1–4 All-rounders</li>
      <li>3–6 Bowlers</li>
      <li>Maximum 7 players from one team</li>
    </ul>

    <h2>Types of Fantasy Contests</h2>
    <p><strong>Head-to-Head:</strong> 2 players, highest score wins. Best for beginners — simple outcomes.</p>
    <p><strong>Small Leagues:</strong> 3–50 players. Better win probability than grand leagues. Good for testing strategies with real stakes.</p>
    <p><strong>Mid Contests:</strong> 51–10,000 players. Moderate competition, good prize structures.</p>
    <p><strong>Grand Leagues:</strong> 10,000–1,000,000 players. Lowest win probability, largest prizes. Requires multi-entry strategy and deep research.</p>

    <h2>How to Get Started — Your First 5 Steps</h2>
    <ol>
      <li><strong>Download Dream11</strong> or create a free account online.</li>
      <li><strong>Start with free practice contests</strong> — no money required, full scoring system.</li>
      <li><strong>Research your first match:</strong> check pitch, form, and playing XI.</li>
      <li><strong>Use FantasyXI AI</strong> to generate multiple teams for free.</li>
      <li><strong>Enter small paid leagues</strong> once comfortable — not grand leagues first.</li>
    </ol>

    <h2>Frequently Asked Questions</h2>
    <div class="faq-item"><div class="faq-q" onclick="toggleFaq(this)">Is fantasy cricket legal in India? <span class="arrow">▼</span></div><div class="faq-a">Yes. Fantasy sports involving skill (not pure chance) are legal in most Indian states under the Supreme Court's ruling. However, some states — including Andhra Pradesh, Assam, Nagaland, Odisha, Sikkim, and Telangana — have restrictions. Always check local laws before participating in paid contests.</div></div>
    <div class="faq-item"><div class="faq-q" onclick="toggleFaq(this)">How much money do I need to start? <span class="arrow">▼</span></div><div class="faq-a">Nothing. You can start completely free with practice contests. When you're ready for paid play, many contests start at ₹11 entry. Start with the minimum and scale up only as you build confidence and strategy.</div></div>
    <div class="faq-item"><div class="faq-q" onclick="toggleFaq(this)">What is the best fantasy cricket platform in India? <span class="arrow">▼</span></div><div class="faq-a">Dream11 is the largest and most popular, with the widest selection of contests and formats. MPL and MyTeam11 are strong alternatives. FantasyXI AI is platform-agnostic — our AI-generated teams can be entered on any platform.</div></div>
    <div class="faq-item"><div class="faq-q" onclick="toggleFaq(this)">Can I use FantasyXI AI teams on any platform? <span class="arrow">▼</span></div><div class="faq-a">Yes. Our AI generates the 11-player lineup with captain and vice-captain. You then manually recreate that team on your chosen platform (Dream11, MPL, etc.). We don't have direct API integration with any platform — the teams are suggestions for you to enter manually.</div></div>

    <div style="margin-top:32px;text-align:center;">
      <a href="/" class="btn btn-gold btn-xl">🤖 Generate Your AI Teams Now →</a>
    </div>
  </article>
</section>"""


def strategy_content():
    return """
<section class="wrap-narrow">
  <div class="blog-article-header">
    <span class="blog-tag">🏆 Dream11 Strategy</span>
    <h1>Dream11 Strategy Guide — Win More With Smart Fantasy Cricket</h1>
    <div class="meta"><span>📅 Updated March 2026</span><span>⏱ 10 min read</span></div>
  </div>
  <article class="prose">
    <h2>The Fundamentals of Dream11 Strategy</h2>
    <p>Dream11 strategy is fundamentally different from simply picking the best cricket players. The challenge is picking the right players for the right contest, with the right captain, at the right ownership level. This guide breaks down everything you need to know.</p>

    <h2>Contest Selection Strategy</h2>
    <p>Your contest selection is as important as your team selection. Here's the framework:</p>
    <div class="highlight">
      <h4>🎯 Contest Selection Framework</h4>
      <ul>
        <li><strong>H2H (2 players):</strong> Safe teams. Win rate target: 55%+. Consistent picks, safe captain.</li>
        <li><strong>Small (2–50 players):</strong> Balanced teams. Win rate target: 30%+. Moderate differentiation.</li>
        <li><strong>Mid (51–5,000):</strong> Balanced/Risky. Win rate target: 5–15%. Differential captain in some teams.</li>
        <li><strong>Grand (5,000+):</strong> Risky mode. Win rate target: 0.5–2%. Maximum differentiation. Multiple entries essential.</li>
      </ul>
    </div>

    <h2>The Multi-Entry Strategy</h2>
    <p>Entering 20 diverse teams in a grand league is not gambling recklessly — it's portfolio management. Each team is a distinct "bet" on a different match outcome scenario. The AI generator ensures these teams are genuinely different (not copies) so your coverage is real.</p>
    <p>The key principle: your 20 teams should collectively have multiple different captain picks, different C/VC combinations, and varying player selections — especially in the positions you're least certain about.</p>

    <h2>Pitch Reading for Strategy</h2>
    <p>Match conditions should dramatically influence your team building. Before every match:</p>
    <ul>
      <li>Check pitch type (batting/bowling friendly) — affects whether to weight batsmen or bowlers</li>
      <li>Check average first-innings T20 score at this venue</li>
      <li>Check weather (dew, rain risk, overcast)</li>
      <li>Research recent head-to-head results at this venue</li>
      <li>Note any batting order changes, player promotions, or role changes</li>
    </ul>

    <h2>Ownership and Differentiation</h2>
    <p>Public ownership drives grand league strategy. If a player is in 70% of teams, they're priced into everyone's lineup — they provide no relative edge. A player in 8% of teams who scores 80 points rockets you past 92% of entries.</p>
    <p>Aim for at least 3–4 "differential" players across your 20 teams — players you believe will outperform their low ownership expectation. The AI generator's Risky mode and Differential Injection settings automate this for you.</p>

    <h2>Season-Long Strategy</h2>
    <p>The best fantasy players think in seasons, not single matches. Track your decisions and outcomes across 30+ matches. Identify your strengths (maybe you're excellent at reading pace bowling conditions) and your weaknesses (maybe you over-trust reputation over recent form). Adjust your strategy based on real data, not intuition.</p>

    <div style="margin-top:32px;text-align:center;">
      <a href="/" class="btn btn-gold btn-xl">🤖 Generate AI Teams in Seconds →</a>
    </div>
  </article>
</section>"""


def captain_content():
    return """
<section class="wrap-narrow">
  <div class="blog-article-header">
    <span class="blog-tag">👑 Captain & VC Strategy</span>
    <h1>Captain & Vice-Captain Strategy — The #1 Fantasy Cricket Decision</h1>
    <div class="meta"><span>📅 Updated March 2026</span><span>⏱ 9 min read</span></div>
  </div>
  <article class="prose">
    <h2>Why Captain Selection Decides Contests</h2>
    <p>The captain earns 2× points and the vice-captain 1.5×. Together they contribute roughly 45–55% of your total team score. Getting both right can overcome mediocre selections elsewhere. Getting both wrong makes great selections elsewhere largely irrelevant.</p>

    <h2>The Three Captain Archetypes</h2>
    <div class="strategy-grid">
      <div class="strategy-card strat-safe">
        <h4>🛡 Safe Captain</h4>
        <p>High-ownership (40–65%), near-certain to score 80+ base points. Best for H2H and small leagues. Consistent but limited upside relative to field.</p>
      </div>
      <div class="strategy-card strat-balanced">
        <h4>⚖️ Balanced Captain</h4>
        <p>Medium ownership (15–35%), strong performer with two-way scoring potential. Often an all-rounder. Best for mid-size contests.</p>
      </div>
      <div class="strategy-card strat-risky">
        <h4>🔥 Differential Captain</h4>
        <p>Low ownership (under 10%), realistic but uncertain high upside. When they fire, you beat 90%+ of the field. Grand leagues only.</p>
      </div>
    </div>

    <h2>All-Rounders as Captain — The Secret Weapon</h2>
    <p>The most consistently undervalued captain picks are quality all-rounders. They have two scoring engines — bat AND ball. A player who takes 2 wickets (50 pts) and scores 35 runs (39 pts) gives you 89 base points — equivalent to a batsman who scores 80 runs and hits 3 sixes. Yet the all-rounder is rarely picked as captain by casual players.</p>
    <p>In mid-size and grand league contexts, all-rounders as captain give you differentiation without the extreme risk of a pure differential. They're the sweet spot of the captain pick spectrum.</p>

    <h2>Vice-Captain Strategy</h2>
    <p>Most players pick their second-favourite player as VC. A better framework:</p>
    <ul>
      <li>Complement your captain type — if captain is a batsman, consider a bowler or all-rounder as VC</li>
      <li>Choose a VC with a different risk profile than your captain</li>
      <li>In 20-team portfolios, use at least 3 different VC picks across your teams</li>
      <li>Never use the same C/VC pair in all 20 teams — it's not actually 20 different bets</li>
    </ul>

    <h2>C/VC Rotation in Multi-Entry Strategies</h2>
    <p>When entering 20 teams, you need meaningful C/VC variety. FantasyXI AI enforces at least 5 unique C/VC combinations by default, and up to 20 unique captains/VCs with the appropriate settings enabled. This ensures genuine coverage across different match-day scenarios.</p>

    <div style="margin-top:32px;text-align:center;">
      <a href="/" class="btn btn-gold btn-xl">🤖 Generate Teams with Smart C/VC Rotation →</a>
    </div>
  </article>
</section>"""


def grand_league_tips_content():
    return """
<section class="wrap-narrow">
  <div class="blog-article-header">
    <span class="blog-tag">🔥 Grand League Tips</span>
    <h1>Grand League Tips — How to Crack the Biggest Fantasy Cricket Prizes</h1>
    <div class="meta"><span>📅 Updated March 2026</span><span>⏱ 8 min read</span></div>
  </div>
  <article class="prose">
    <h2>Understanding Grand League Dynamics</h2>
    <p>A grand league on Dream11 might have 200,000 entries for a single IPL match. The first prize can be ₹10 crore or more. The mathematics are brutal — but the strategy that cracks grand leagues is learnable and systematic.</p>
    <p>The core insight: <strong>grand leagues are won by being right when the crowd is wrong.</strong> Popular picks earn you nothing relative to the majority. Differentials — players the crowd undervalues — are how you outrun 200,000 entries in one grand match-day performance.</p>

    <h2>10 Actionable Grand League Tips</h2>

    <h3>1. Enter Multiple Teams</h3>
    <p>A single team in a 200,000-entry grand league has almost no realistic chance of winning. Enter 10–20 teams with meaningful diversity across captains, VCs, and player selections. Our AI generates these for free.</p>

    <h3>2. Use Risky Mode for Grand Leagues</h3>
    <p>Safe picks belong in small leagues. Grand leagues require differentials. Set FantasyXI AI to Risky mode, enable Differential Injection, and let the algorithm weight low-ownership picks appropriately.</p>

    <h3>3. Research Expected Ownership</h3>
    <p>Before selecting your captain, estimate how many entries will have each candidate. Social media, fantasy forums, and Dream11's player selection percentage show this data. Avoid captains with 50%+ expected ownership in grand leagues.</p>

    <h3>4. Identify the Match-Day Pitch Report</h3>
    <p>Pitch conditions on match day drive which player type tops the scoring charts. A spinner who takes 4 wickets on a turning track can score 150+ points and be in only 5% of teams. Read the pitch report and weight your captain selection accordingly.</p>

    <h3>5. Lock 2–3 Core Players, Leave 8–9 Flexible</h3>
    <p>Lock your highest-conviction picks (typically 2–3 players) across all teams. Let the AI vary the rest to create genuine diversity across your 20-team portfolio.</p>

    <h3>6. Never Copy Public Fantasy Expert Teams</h3>
    <p>If everyone copies the "expert team" from a popular YouTube channel, that team has 15–20% of entries in the grand league. You're competing for the same outcome as 30,000 other people. Build your own teams independently — or use AI-generated teams that the crowd hasn't seen.</p>

    <h3>7. Wait for the Playing XI Before Finalising</h3>
    <p>Player news changes everything. A star player who is rested, a young opener who gets promoted up the order, or a bowler making his seasonal debut — these changes should influence your captain choice significantly. Wait for the confirmed XI.</p>

    <h3>8. Use Exposure Limits Intelligently</h3>
    <p>Set your exposure limit at 70–75%. This means your best players appear in about 14–15 of your 20 teams — giving you core coverage without over-concentration. If that player scores 0, only 14 of your 20 teams are affected.</p>

    <h3>9. Have Conviction on at Least One Differential</h3>
    <p>Pure randomisation doesn't win grand leagues — informed differentiation does. Find one player you genuinely believe will outperform their ownership expectation, based on research (not intuition), and make them captain in 4–6 of your teams.</p>

    <h3>10. Track Your Grand League Win Rate</h3>
    <p>Grand league winning is a long-term game. Track your results over 3–6 months. Note which strategies, which captain picks, and which match types yield the best results. Fantasy cricket rewards learning and iteration far more than luck.</p>

    <div style="margin-top:32px;text-align:center;">
      <a href="/" class="btn btn-gold btn-xl">🤖 Generate Grand League Teams Now →</a>
    </div>
  </article>
</section>"""


# =============================================================================
# ─── ROUTES ──────────────────────────────────────────────────────────────────
# =============================================================================

@app.route("/")
def home():
    td = load_teams()
    md = load_matches()
    players_json = {t["team"]: t["players"][:11] for t in td["teams"]}
    return render_template_string(
        HOME_PAGE,
        tournament=td.get("tournament", "FantasyXI AI"),
        matches=md["matches"],
        all_teams=td["teams"],
        players_json=players_json,
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
    session["gen"] = {"teams": teams, "team1": team1, "team2": team2, "mode": mode, "venue": venue}
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
    gen      = session.get("gen", {})
    teams    = gen.get("teams", [])
    if not teams: return "No teams found. Please generate teams first.", 400
    team1    = gen.get("team1", "T1")
    team2    = gen.get("team2", "T2")
    mode     = gen.get("mode", "balanced").upper()
    venue    = gen.get("venue", "")
    unlocked = session.get("unlocked", False)
    max_idx  = len(teams) if unlocked else 3
    role_abbr = {"Wicketkeeper-Batsman":"WK","Batsman":"BAT","All-rounder":"AR","Bowler":"BOWL"}
    risk_color = {"Low":"#00e5a0","Medium":"#4db8ff","High":"#ff4d6d"}
    cards_html = ""
    for idx, t in enumerate(teams[:max_idx]):
        players_rows = ""
        for p in t["players"]:
            is_c  = p["name"] == t["captain"]
            is_vc = p["name"] == t["vice_captain"]
            tag   = " <b style='color:#f5c842'>(C)</b>" if is_c else (" <b style='color:#4db8ff'>(VC)</b>" if is_vc else "")
            rc    = risk_color.get(p["risk_level"], "#fff")
            ra    = role_abbr.get(p["role"], p["role"])
            players_rows += f"""<tr>
              <td style="padding:5px 8px;border-bottom:1px solid #e8e8e8;">{p["name"]}{tag}</td>
              <td style="padding:5px 8px;border-bottom:1px solid #e8e8e8;color:#555;font-size:.8rem;">{ra}</td>
              <td style="padding:5px 8px;border-bottom:1px solid #e8e8e8;text-align:center;">
                <span style="background:{rc}22;color:{rc};font-size:.7rem;font-weight:700;padding:2px 7px;border-radius:4px;border:1px solid {rc}55;">{p["risk_level"]}</span>
              </td></tr>"""
        cards_html += f"""<div class="team-card">
          <div class="card-hdr"><span class="team-num">Team {idx+1}</span><span class="badge">{"FREE" if idx<3 else "UNLOCKED"}</span></div>
          <div class="cv-strip">
            <div class="cv-box"><div class="cv-lbl">Captain 2×</div><div class="cv-name cap">{t["captain"]}</div></div>
            <div class="cv-box"><div class="cv-lbl">Vice Captain 1.5×</div><div class="cv-name vc">{t["vice_captain"]}</div></div>
          </div>
          <table width="100%" cellspacing="0"><thead><tr style="background:#f8f8f8;"><th style="padding:5px 8px;text-align:left;font-size:.72rem;color:#888;">PLAYER</th><th style="padding:5px 8px;text-align:left;font-size:.72rem;color:#888;">ROLE</th><th style="padding:5px 8px;text-align:center;font-size:.72rem;color:#888;">RISK</th></tr></thead><tbody>{players_rows}</tbody></table>
          <div style="padding:7px 10px;background:#f8f8f8;border-top:1px solid #eee;font-size:.65rem;color:#888;text-align:center;">{t["from_t1"]} from {team1} · {t["from_t2"]} from {team2}</div>
        </div>"""
    venue_str = f"<p style='margin:2px 0 0;font-size:.8rem;color:#666;'>📍 {venue}</p>" if venue else ""
    html = f"""<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8"><title>FantasyXI AI — {team1} vs {team2}</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box;}}body{{font-family:Arial,sans-serif;background:#fff;color:#111;font-size:13px;}}
.site-header{{background:linear-gradient(135deg,#f5c842,#d4a212);padding:14px 24px;display:flex;justify-content:space-between;align-items:center;}}
.site-header h1{{font-size:1.1rem;font-weight:800;color:#000;}}
.meta-bar{{background:#111;color:#fff;padding:10px 24px;display:flex;align-items:center;gap:16px;flex-wrap:wrap;}}
.meta-bar .vs{{font-size:1.1rem;font-weight:800;}}
.meta-bar .vs em{{color:#f5c842;font-style:normal;margin:0 6px;font-size:.8rem;}}
.print-note{{background:#fffbea;border:1px solid #f5c842;border-radius:8px;padding:12px 20px;margin:18px 20px;font-size:.82rem;color:#7a5c00;display:flex;align-items:center;gap:10px;}}
.print-note button{{background:linear-gradient(135deg,#f5c842,#d4a212);border:none;border-radius:6px;padding:7px 18px;font-size:.82rem;font-weight:700;cursor:pointer;color:#000;}}
.teams-wrap{{display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:14px;padding:0 20px 30px;}}
.team-card{{border:1px solid #ddd;border-radius:10px;overflow:hidden;break-inside:avoid;}}
.card-hdr{{background:linear-gradient(135deg,#1a1e30,#0d1020);padding:9px 13px;display:flex;justify-content:space-between;align-items:center;}}
.team-num{{color:#f5c842;font-weight:800;font-size:.88rem;letter-spacing:2px;}}
.badge{{background:#00e5a0;color:#000;font-size:.6rem;font-weight:800;padding:2px 9px;border-radius:100px;}}
.cv-strip{{display:flex;gap:6px;padding:9px 10px 6px;background:#fafafa;}}
.cv-box{{flex:1;border:1px solid #eee;border-radius:6px;padding:6px 8px;text-align:center;}}
.cv-lbl{{font-size:.58rem;color:#999;text-transform:uppercase;margin-bottom:2px;font-weight:600;}}
.cv-name{{font-weight:700;font-size:.78rem;}}
.cv-name.cap{{color:#b8860b;}} .cv-name.vc{{color:#1a6fa6;}}
@media print{{body{{-webkit-print-color-adjust:exact;print-color-adjust:exact;}}.print-note{{display:none!important;}}.teams-wrap{{grid-template-columns:repeat(2,1fr);gap:10px;padding:0 10px 20px;}}@page{{margin:12mm 10mm;size:A4;}}}}
</style></head><body>
<div class="site-header"><div><h1>⚡ FantasyXI AI — fantasyxi.in</h1><p style="font-size:.72rem;color:#222;">AI-powered fantasy cricket teams</p></div><div style="text-align:right;font-size:.75rem;color:#222;">{len(teams[:max_idx])} Teams · {mode} Mode · {datetime.date.today().strftime("%d %b %Y")}</div></div>
<div class="meta-bar"><span class="vs">{team1}<em>VS</em>{team2}</span>{venue_str}</div>
<div class="print-note"><span>💡 Click the button to save as PDF</span><button onclick="window.print()">🖨 Save as PDF</button></div>
<div class="teams-wrap">{cards_html}</div>
<script>setTimeout(function(){{if(document.visibilityState==='visible')window.print();}},800);</script>
</body></html>"""
    return Response(html, mimetype="text/html")


# ─── CONTENT PAGES ────────────────────────────────────────────────────────────

@app.route("/fantasy-cricket-guide")
def fantasy_cricket_guide():
    return page_shell(
        "Fantasy Cricket Guide — How Fantasy Cricket Works, Scoring, Tips",
        "Complete guide to fantasy cricket — how scoring works, team rules, contest types, captain strategy, and expert tips for Dream11 and all major platforms.",
        "/fantasy-cricket-guide", "guide", guide_content()
    )

@app.route("/dream11-strategy")
def dream11_strategy():
    return page_shell(
        "Dream11 Strategy Guide — Win More Fantasy Cricket Contests",
        "Comprehensive Dream11 strategy guide covering contest selection, multi-entry portfolio strategy, pitch reading, ownership analysis, and grand league tactics.",
        "/dream11-strategy", "strategy", strategy_content()
    )

@app.route("/captain-vc-strategy")
def captain_vc_strategy():
    return page_shell(
        "Captain & Vice-Captain Strategy for Fantasy Cricket",
        "Master captain and vice-captain selection in fantasy cricket. Learn safe, balanced, and differential captain strategies with expert tips for Dream11 grand leagues.",
        "/captain-vc-strategy", "strategy", captain_content()
    )

@app.route("/grand-league-tips")
def grand_league_tips():
    return page_shell(
        "Grand League Tips — How to Win Dream11 Grand Leagues",
        "10 proven grand league tips for Dream11: differential captain picks, multi-entry strategy, ownership analysis, pitch reading, and bankroll management.",
        "/grand-league-tips", "strategy", grand_league_tips_content()
    )

# ─── BLOG ─────────────────────────────────────────────────────────────────────

@app.route("/blog")
def blog():
    cards = ""
    for post in BLOG_POSTS:
        cards += f"""
        <a href="/blog/{post['slug']}" class="blog-card">
          <div class="blog-card-img">{post['icon']}</div>
          <div class="blog-card-body">
            <span class="blog-tag">{post['tag']}</span>
            <div class="blog-card-title">{post['title']}</div>
            <div class="blog-card-excerpt">{post['excerpt']}</div>
            <div class="blog-card-meta"><span>📅 {post['date']}</span><span>⏱ {post['read_time']}</span></div>
          </div>
        </a>"""
    content = f"""
    <section class="wrap">
      <div style="margin-bottom:28px;">
        <div class="hero-badge">📝 Expert Articles</div>
        <h1 class="section-title" style="margin-top:14px;">Fantasy Cricket Blog</h1>
        <p class="section-sub">Expert guides, proven strategies, and in-depth analysis to help you win more fantasy cricket contests — from beginner basics to advanced grand league tactics.</p>
      </div>
      <div class="blog-grid">{cards}</div>
    </section>"""
    return page_shell(
        "Fantasy Cricket Blog — Strategy Guides, Tips & Expert Analysis",
        "Expert fantasy cricket articles covering Dream11 strategy, grand league tips, captain selection, beginner guides, and winning strategies for IPL and T20 World Cup.",
        "/blog", "blog", content
    )

@app.route("/blog/<slug>")
def blog_post(slug):
    post = BLOG_INDEX.get(slug)
    if not post:
        return "Article not found", 404
    content = f"""
    <section class="wrap-narrow">
      <div class="blog-article-header">
        <span class="blog-tag">{post['tag']}</span>
        <h1>{post['title']}</h1>
        <div class="meta"><span>📅 {post['date']}</span><span>⏱ {post['read_time']}</span><span>👤 FantasyXI Team</span></div>
      </div>
      <article class="prose">
        {post['body']}
      </article>
      <div style="margin-top:40px;padding:24px;background:var(--s2);border:1px solid var(--brd);border-radius:var(--r);text-align:center;">
        <div style="font-family:'Barlow Condensed',sans-serif;font-size:1.2rem;font-weight:800;letter-spacing:1px;margin-bottom:8px;">Ready to put strategy into action?</div>
        <p style="color:var(--txt3);font-size:.85rem;margin-bottom:16px;">Generate 20 unique AI fantasy cricket teams for today's match — free, instant, no login.</p>
        <a href="/" class="btn btn-gold btn-lg">🤖 Generate AI Teams Now →</a>
      </div>
      <div style="margin-top:32px;">
        <div class="sh">More Articles</div>
        <div class="blog-grid">"""
    for p in BLOG_POSTS:
        if p["slug"] != slug:
            content += f"""<a href="/blog/{p['slug']}" class="blog-card">
              <div class="blog-card-img" style="height:90px;">{p['icon']}</div>
              <div class="blog-card-body"><span class="blog-tag">{p['tag']}</span><div class="blog-card-title">{p['title']}</div></div>
            </a>"""
    content += """</div></div></section>"""
    return page_shell(
        post["title"],
        post["excerpt"],
        f"/blog/{slug}", "blog", content
    )


# ─── LEGAL / STATIC PAGES ─────────────────────────────────────────────────────

def legal_shell(title, body, slug):
    content = f"""<div class="legal-wrap">{body}</div>"""
    return page_shell(title, title + " — FantasyXI AI", slug, "", content)

@app.route("/privacy")
def privacy():
    return legal_shell("Privacy Policy", """
<h1>Privacy Policy</h1><p class="last-updated">Last updated: February 2026</p>
<h2>Introduction</h2><p>FantasyXI AI ("we","our","us") is committed to protecting your privacy. This Policy explains how we collect, use, and safeguard information when you visit fantasyxi.in.</p>
<h2>Information We Collect</h2><ul><li><strong>Log Data:</strong> IP addresses, browser type, pages visited, referral URL.</li><li><strong>Cookies:</strong> We and advertising partners (Google AdSense) use cookies for analytics and personalised ads.</li><li><strong>Contact Form Data:</strong> Name, email, subject, and message when you contact us.</li><li><strong>Session Data:</strong> Temporary server-side data to display your generated teams within a session.</li></ul>
<h2>Google AdSense</h2><p>We use Google AdSense. Google uses cookies to serve ads based on your site visits. Opt out at <a href="https://www.google.com/settings/ads" target="_blank" rel="noopener">google.com/settings/ads</a>.</p>
<h2>Children's Privacy</h2><p>This site is for users 18+. We do not knowingly collect data from minors.</p>
<h2>Contact</h2><p>Questions? Use our <a href="/contact">Contact page</a>.</p>""", "/privacy")

@app.route("/terms")
def terms():
    return legal_shell("Terms & Conditions", """
<h1>Terms &amp; Conditions</h1><p class="last-updated">Last updated: February 2026</p>
<h2>Acceptance</h2><p>By using FantasyXI AI, you agree to these Terms.</p>
<h2>Age Restriction</h2><p>18+ only. By using this site you confirm you are of legal age.</p>
<h2>No Guarantee</h2><p>FantasyXI AI is an informational and entertainment tool only. We make no guarantee of winnings.</p>
<h2>Intellectual Property</h2><p>Not affiliated with Dream11, MyTeam11, ICC, BCCI, or any official body.</p>
<h2>Governing Law</h2><p>These Terms are governed by the laws of India.</p>
<h2>Contact</h2><p>Questions? <a href="/contact">Contact us</a>.</p>""", "/terms")

@app.route("/disclaimer")
def disclaimer():
    return legal_shell("Disclaimer", """
<h1>Disclaimer</h1><p class="last-updated">Last updated: February 2026</p>
<h2>General</h2><p>All content on FantasyXI AI is for general informational and entertainment purposes only.</p>
<h2>Fantasy Sports Risk</h2><p>Fantasy sports involve financial risk. FantasyXI AI does not guarantee any winnings. Play responsibly.</p>
<h2>Affiliation</h2><p>FantasyXI AI is not affiliated with Dream11, MyTeam11, ICC, BCCI, or any fantasy sports platform.</p>
<h2>18+ Only</h2><p>This website is strictly for users aged 18 and above.</p>""", "/disclaimer")

@app.route("/about")
def about():
    return legal_shell("About Us", """
<h1>About FantasyXI AI</h1><p class="last-updated">India's #1 AI Fantasy Cricket Team Generator</p>
<h2>Our Mission</h2><p>FantasyXI AI was built to democratise professional-grade fantasy cricket strategy. Instead of spending hours manually creating teams, players of all skill levels can use our AI engine to generate 20 optimised, unique Dream11 teams in seconds.</p>
<h2>What Makes Us Different</h2><ul><li>Multi-layer AI probability weighting — not random selection</li><li>Intelligent C/VC rotation across all 20 teams</li><li>Player exposure control to maintain portfolio health</li><li>Lock/exclude individual players for precision control</li><li>Differential injection for grand league strategy</li><li>100% free — no login, no payment required</li></ul>
<h2>Disclaimer</h2><p>FantasyXI AI is an independent informational tool. It is not affiliated with Dream11, MyTeam11, ICC, BCCI, or any official cricket body. Fantasy sports involve financial risk — play responsibly. 18+ only.</p>
<p>Questions? <a href="/contact">Contact us</a>.</p>""", "/about")

@app.route("/contact")
def contact():
    body = """
<h1>Contact Us</h1><p class="last-updated">We respond within 48 business hours.</p>
<h2>Send a Message</h2>
<form class="contact-form" id="contactForm" onsubmit="submitForm(event)" novalidate>
  <div class="form-group"><label for="cf-name">Name *</label><input type="text" id="cf-name" placeholder="Your name" required autocomplete="name"></div>
  <div class="form-group"><label for="cf-email">Email *</label><input type="email" id="cf-email" placeholder="you@example.com" required autocomplete="email"></div>
  <div class="form-group"><label for="cf-subject">Subject</label><select id="cf-subject"><option>General Enquiry</option><option>Bug Report</option><option>Feature Request</option><option>Squad/Data Update</option><option>Partnership</option><option>Other</option></select></div>
  <div class="form-group"><label for="cf-msg">Message *</label><textarea id="cf-msg" placeholder="Your message..." required></textarea></div>
  <button type="submit" class="btn btn-gold btn-lg" id="submitBtn">Send Message →</button>
</form>
<div id="formMsg" style="display:none;background:rgba(0,229,160,.08);border:1px solid rgba(0,229,160,.25);border-radius:8px;padding:13px 16px;font-size:.82rem;color:#00e5a0;margin-top:16px;">✅ Thank you! We'll get back to you within 48 hours.</div>
<div id="formError" style="display:none;background:rgba(255,77,109,.08);border:1px solid rgba(255,77,109,.25);border-radius:8px;padding:13px 16px;font-size:.82rem;color:#ff4d6d;margin-top:12px;"></div>
<script>
function submitForm(e){
  e.preventDefault();
  var name=document.getElementById('cf-name').value.trim(),email=document.getElementById('cf-email').value.trim();
  var subject=document.getElementById('cf-subject').value,msg=document.getElementById('cf-msg').value.trim();
  var errBox=document.getElementById('formError'),btn=document.getElementById('submitBtn');
  errBox.style.display='none';
  if(!name||!email||!msg){showToast('Please fill all required fields.','#ff4d6d');return;}
  if(!email.includes('@')){showToast('Invalid email.','#ff4d6d');return;}
  btn.disabled=true;btn.textContent='⏳ Sending…';
  var timedOut=false;
  var timer=setTimeout(function(){timedOut=true;document.getElementById('contactForm').style.display='none';document.getElementById('formMsg').style.display='block';},12000);
  fetch('/send_contact',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:name,email:email,subject:subject,message:msg})})
  .then(function(r){return r.json();})
  .then(function(d){clearTimeout(timer);if(timedOut)return;if(d.success){document.getElementById('contactForm').style.display='none';document.getElementById('formMsg').style.display='block';}else{errBox.textContent='❌ '+(d.error||'Error. Please try again.');errBox.style.display='block';btn.disabled=false;btn.textContent='Send Message →';}})
  .catch(function(){clearTimeout(timer);if(timedOut)return;errBox.textContent='❌ Network error.';errBox.style.display='block';btn.disabled=false;btn.textContent='Send Message →';});
}
</script>"""
    return legal_shell("Contact Us", body, "/contact")


@app.route("/send_contact", methods=["POST"])
def send_contact():
    data    = request.get_json(silent=True) or {}
    name    = data.get("name", "").strip()
    email   = data.get("email", "").strip()
    subject = data.get("subject", "General").strip()
    message = data.get("message", "").strip()
    if not name or not email or not message:
        return jsonify({"success": False, "error": "Please fill in all required fields."}), 400
    if "@" not in email or "." not in email.split("@")[-1]:
        return jsonify({"success": False, "error": "Please enter a valid email."}), 400
    t = threading.Thread(target=_smtp_send, args=(name, email, subject, message), daemon=True)
    t.start()
    return jsonify({"success": True})


@app.route("/robots.txt")
def robots():
    return Response("""User-agent: *
Allow: /
Disallow: /generate
Disallow: /export_pdf
Disallow: /unlock
Sitemap: https://fantasyxi.in/sitemap.xml
""", mimetype="text/plain")


@app.route("/sitemap.xml")
def sitemap():
    today = datetime.date.today().isoformat()
    urls = [
        ("https://fantasyxi.in/", "1.0", "daily"),
        ("https://fantasyxi.in/fantasy-cricket-guide", "0.9", "weekly"),
        ("https://fantasyxi.in/dream11-strategy", "0.9", "weekly"),
        ("https://fantasyxi.in/captain-vc-strategy", "0.8", "weekly"),
        ("https://fantasyxi.in/grand-league-tips", "0.8", "weekly"),
        ("https://fantasyxi.in/blog", "0.9", "weekly"),
        ("https://fantasyxi.in/about", "0.7", "monthly"),
        ("https://fantasyxi.in/contact", "0.6", "monthly"),
        ("https://fantasyxi.in/privacy", "0.4", "yearly"),
        ("https://fantasyxi.in/terms", "0.4", "yearly"),
        ("https://fantasyxi.in/disclaimer", "0.4", "yearly"),
    ] + [(f"https://fantasyxi.in/blog/{p['slug']}", "0.85", "weekly") for p in BLOG_POSTS]
    xml = '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
    for loc, pri, freq in urls:
        xml += f"  <url><loc>{loc}</loc><lastmod>{today}</lastmod><changefreq>{freq}</changefreq><priority>{pri}</priority></url>\n"
    xml += "</urlset>"
    return Response(xml, mimetype="application/xml")


if __name__ == "__main__":
    app.run(debug=True, port=5000)
