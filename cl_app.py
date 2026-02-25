# =============================================================================
# AI Fantasy Team Generator — Flask app | v3.2
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
# Uses Gmail SMTP with App Password (NOT your regular Gmail password).
# Steps to get App Password:
#   1. Go to myaccount.google.com → Security → 2-Step Verification (enable it)
#   2. Then go to myaccount.google.com → Security → App Passwords
#   3. Generate a password for "Mail" → copy the 16-character code
#   4. Paste it below as SMTP_PASSWORD
SMTP_HOST     = "smtp.gmail.com"
SMTP_PORT     = 587
SMTP_USER     = "tehm8111@gmail.com"  # your Gmail address
SMTP_PASSWORD = "idkl poic jbvh ysou"  # 16-char Gmail App Password
EMAIL_TO      = "tehm8111@gmail.com"  # inbox to receive messages

def _smtp_send(name, email, subject, message):
    """Runs in background thread — never blocks the HTTP response."""
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"]  = f"[FantasyXI Contact] {subject} — from {name}"
        msg["From"]     = SMTP_USER
        msg["To"]       = EMAIL_TO
        msg["Reply-To"] = email

        html_body = f"""
        <div style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;background:#0f1220;color:#e2e8f8;border-radius:12px;overflow:hidden;">
          <div style="background:linear-gradient(135deg,#f5c842,#d4a212);padding:18px 28px;">
            <h2 style="margin:0;color:#000;font-size:1.3rem;">⚡ New Contact Form Submission</h2>
            <p style="margin:4px 0 0;color:#222;font-size:.85rem;">AI Fantasy Team Generator — fantasyxi.in</p>
          </div>
          <div style="padding:28px;">
            <table style="width:100%;border-collapse:collapse;">
              <tr><td style="padding:8px 0;color:#8896b8;font-size:.8rem;width:100px;">Name</td><td style="padding:8px 0;font-weight:600;">{name}</td></tr>
              <tr><td style="padding:8px 0;color:#8896b8;font-size:.8rem;">Email</td><td style="padding:8px 0;"><a href="mailto:{email}" style="color:#f5c842;">{email}</a></td></tr>
              <tr><td style="padding:8px 0;color:#8896b8;font-size:.8rem;">Subject</td><td style="padding:8px 0;">{subject}</td></tr>
            </table>
            <div style="margin-top:20px;background:#131728;border-radius:8px;padding:18px;border-left:3px solid #f5c842;">
              <p style="margin:0 0 8px;color:#8896b8;font-size:.75rem;text-transform:uppercase;letter-spacing:1px;">Message</p>
              <p style="margin:0;line-height:1.7;white-space:pre-wrap;">{message}</p>
            </div>
            <p style="margin-top:20px;font-size:.75rem;color:#4a5578;">
              Reply directly to this email to respond to {name}.<br>
              Sent from fantasyxi.in contact form.
            </p>
          </div>
        </div>"""
        text_body = f"New contact form submission\n\nName: {name}\nEmail: {email}\nSubject: {subject}\n\nMessage:\n{message}"

        msg.attach(MIMEText(text_body, "plain"))
        msg.attach(MIMEText(html_body, "html"))

        # 10-second timeout on connect AND read — never hangs forever
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=10) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.sendmail(SMTP_USER, EMAIL_TO, msg.as_string())
        print(f"[Email OK] Contact from {name} <{email}>")
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
            tries = random.choices(free_pool, weights=adj_weights,
                                   k=min(len(free_pool), need * 6))
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
                for p in low_appear1 + low_appear2:
                    locked_ids.add(p["id"])

            sel1 = pick_unique(pool1, w1, n1, locked_ids)
            sel2 = pick_unique(pool2, w2, n2, locked_ids)

            if min_diff > 0 and idx >= 5:
                for p in low_appear1 + low_appear2:
                    locked_ids.discard(p["id"])
                for lid in adv.get("locked", []):
                    locked_ids.add(lid)

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
                if alt:
                    vp, vws = zip(*alt); vp, vws = list(vp), list(vws)

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
/* ══════════════════════════════════════════════
   DESIGN SYSTEM — Premium Dark Gold
   Fonts: Barlow Condensed (display) + DM Sans (body)
   ══════════════════════════════════════════════ */
:root {
  --bg:   #060810;
  --s1:   #0b0e1c;
  --s2:   #0f1220;
  --s3:   #131728;
  --s4:   #181c30;
  --s5:   #1e2238;
  --brd:  #1d2140;
  --brd2: #2a3060;
  --brd3: #374070;
  --gld:      #f5c842;
  --gld2:     #d4a212;
  --gld3:     #fad96a;
  --gld-glow: rgba(245,200,66,.15);
  --gld-dim:  rgba(245,200,66,.08);
  --ora: #ff7043;
  --grn: #00e5a0;
  --blu: #4db8ff;
  --red: #ff4d6d;
  --pur: #a78bfa;
  --cyn: #22d3ee;
  --txt:  #e2e8f8;
  --txt2: #8896b8;
  --txt3: #4a5578;
  --txt4: #2d3555;
  --r:  14px;
  --r2: 10px;
  --r3: 8px;
  --shadow: 0 8px 32px rgba(0,0,0,.6);
  --shadow2: 0 2px 12px rgba(0,0,0,.4);
  --glow-gld: 0 0 30px rgba(245,200,66,.12), 0 0 60px rgba(245,200,66,.06);
  --hdr-h:  58px;
  --step-h: 52px;
}

*, *::before, *::after { margin:0; padding:0; box-sizing:border-box; }
html { scroll-behavior: smooth; }
body {
  font-family: 'DM Sans', -apple-system, BlinkMacSystemFont, sans-serif;
  background: var(--bg);
  color: var(--txt);
  min-height: 100vh;
  overflow-x: hidden;
  font-size: 15px;
  line-height: 1.65;
  padding-top: calc(var(--hdr-h) + var(--step-h));
}

body::before {
  content: '';
  position: fixed; inset: 0; z-index: 0; pointer-events: none;
  background-image:
    radial-gradient(ellipse 80% 50% at 50% -5%, rgba(245,200,66,.05), transparent 60%),
    radial-gradient(ellipse 40% 30% at 85% 110%, rgba(77,184,255,.04), transparent 50%),
    linear-gradient(rgba(255,255,255,.008) 1px, transparent 1px),
    linear-gradient(90deg, rgba(255,255,255,.008) 1px, transparent 1px);
  background-size: 100%, 100%, 56px 56px, 56px 56px;
}
.z1 { position: relative; z-index: 1; }

::-webkit-scrollbar { width: 5px; }
::-webkit-scrollbar-track { background: var(--s1); }
::-webkit-scrollbar-thumb { background: var(--brd3); border-radius: 3px; }

header {
  position: fixed; top: 0; left: 0; right: 0;
  z-index: 900;
  height: var(--hdr-h);
  background: rgba(6,8,16,.97);
  backdrop-filter: blur(24px); -webkit-backdrop-filter: blur(24px);
  border-bottom: 1px solid var(--brd);
  display: flex; align-items: center;
  padding: 0 32px;
}
.logo-wrap { display: flex; align-items: center; }
.logo {
  font-family: 'Barlow Condensed', sans-serif; font-size: 1.25rem; font-weight: 800;
  letter-spacing: 2px; white-space: nowrap;
  background: linear-gradient(135deg, var(--gld3) 0%, var(--gld) 40%, var(--ora) 100%);
  -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text;
  text-decoration: none;
}
.logo-badge {
  font-size: .56rem; color: var(--txt3); letter-spacing: 1.5px; text-transform: uppercase;
  background: var(--s3); border: 1px solid var(--brd); padding: 3px 9px; border-radius: 6px;
}
.hdr-nav { margin-left: auto; display: flex; gap: 4px; align-items: center; }
.hdr-nav a {
  color: var(--txt2); text-decoration: none; font-size: .82rem; font-weight: 500;
  padding: 6px 14px; border-radius: 8px; border: 1px solid transparent;
  transition: all .18s; letter-spacing: .2px;
}
.hdr-nav a:hover { color: var(--txt); background: var(--s2); border-color: var(--brd); }
.hdr-nav a.cta {
  background: linear-gradient(135deg, var(--gld), var(--gld2));
  color: #000; border-color: transparent; font-weight: 700; letter-spacing: .8px;
  margin-left: 8px; padding: 7px 18px;
}
.hdr-nav a.cta:hover { box-shadow: 0 4px 16px var(--gld-glow); transform: translateY(-1px); }

.step-bar {
  position: fixed;
  top: var(--hdr-h);
  left: 0; right: 0;
  z-index: 850;
  height: var(--step-h);
  background: rgba(11,14,28,.98);
  backdrop-filter: blur(20px); -webkit-backdrop-filter: blur(20px);
  border-bottom: 1px solid var(--brd);
  display: flex; align-items: center; justify-content: center;
  padding: 0 32px;
}
.step-bar-inner {
  display: flex; align-items: center;
  width: 100%; max-width: 680px;
}
.step { display: flex; align-items: center; gap: 8px; flex: 1; }
.step-num {
  width: 26px; height: 26px; border-radius: 50%;
  border: 2px solid var(--brd2);
  display: flex; align-items: center; justify-content: center;
  font-family: 'Barlow Condensed', sans-serif; font-size: .75rem; font-weight: 800;
  color: var(--txt3); flex-shrink: 0; transition: all .3s;
}
.step-lbl { font-size: .7rem; color: var(--txt3); transition: color .3s; white-space: nowrap; font-weight: 500; }
.step-line { flex: 1; height: 1px; background: var(--brd); margin: 0 6px; transition: background .3s; }
.step.done .step-num { background: var(--grn); border-color: var(--grn); color: #000; }
.step.done .step-lbl  { color: var(--grn); }
.step.done .step-line { background: var(--grn); }
.step.active .step-num {
  background: var(--gld); border-color: var(--gld); color: #000;
  box-shadow: 0 0 0 3px rgba(245,200,66,.22), 0 0 14px rgba(245,200,66,.18);
}
.step.active .step-lbl { color: var(--gld); font-weight: 600; }

@media(max-width:500px) {
  .step-lbl { display: none; }
  .step-line { margin: 0 3px; }
  .step-bar  { padding: 0 16px; }
}

.wrap { max-width: 1200px; margin: 0 auto; padding: 26px 20px 90px; }

.sh {
  font-family: 'Barlow Condensed', sans-serif; font-size: 1rem; font-weight: 700;
  letter-spacing: 2.5px; text-transform: uppercase;
  color: var(--gld); margin-bottom: 16px;
  display: flex; align-items: center; gap: 12px;
}
.sh::after { content: ''; flex: 1; height: 1px; background: linear-gradient(to right, var(--brd2), transparent); }
.sh small { font-size: .62rem; color: var(--txt3); letter-spacing: 1px; font-weight: 400; }

.tab-bar {
  display: flex; gap: 3px; background: var(--s1); border: 1px solid var(--brd);
  border-radius: 11px; padding: 4px; width: fit-content; margin-bottom: 20px;
}
.tab-btn {
  padding: 7px 18px; border-radius: 8px; border: none; background: transparent;
  color: var(--txt3); font-family: 'DM Sans', sans-serif; font-size: .8rem; font-weight: 500;
  cursor: pointer; transition: all .2s; letter-spacing: .3px;
}
.tab-btn.active { background: var(--s3); color: var(--txt); border: 1px solid var(--brd2); box-shadow: var(--shadow2); }

.match-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(285px, 1fr)); gap: 10px; margin-bottom: 26px; }
.match-card {
  background: var(--s2); border: 1px solid var(--brd); border-radius: var(--r);
  padding: 16px 18px 14px; cursor: pointer; transition: all .22s;
  position: relative; overflow: hidden;
}
.match-card::before {
  content: ''; position: absolute; inset: 0;
  background: linear-gradient(135deg, rgba(245,200,66,.04), transparent 60%);
  opacity: 0; transition: opacity .22s;
}
.match-card:hover { border-color: rgba(245,200,66,.45); transform: translateY(-3px); box-shadow: var(--shadow); }
.match-card:hover::before { opacity: 1; }
.match-card.selected { border-color: var(--gld); background: var(--gld-dim); box-shadow: 0 0 0 1px var(--gld), var(--shadow); }
.match-time {
  position: absolute; top: 10px; right: 10px;
  background: rgba(245,200,66,.1); border: 1px solid rgba(245,200,66,.2);
  color: var(--gld); font-size: .58rem; font-weight: 700;
  padding: 2px 8px; border-radius: 100px; letter-spacing: .8px;
}
.match-id-tag { font-size: .6rem; color: var(--txt3); letter-spacing: .8px; text-transform: uppercase; margin-bottom: 8px; }
.match-vs {
  font-family: 'Barlow Condensed', sans-serif; font-size: 1.45rem; font-weight: 800;
  letter-spacing: 1px; text-align: center; line-height: 1.1;
}
.match-vs em { color: var(--gld); font-style: normal; margin: 0 8px; font-size: .85rem; font-weight: 400; }
.match-venue { font-size: .63rem; color: var(--txt3); text-align: center; margin-top: 6px; }

.mode-grid { display: grid; grid-template-columns: repeat(3,1fr); gap: 12px; margin-bottom: 26px; }
@media(max-width:580px) { .mode-grid { grid-template-columns:1fr; } }
.mode-card {
  border-radius: var(--r); padding: 22px 16px; text-align: center;
  cursor: pointer; border: 2px solid transparent; transition: all .25s;
  position: relative; overflow: hidden;
}
.mode-card::after {
  content: ''; position: absolute; inset: 0; opacity: 0; transition: opacity .25s;
  background: radial-gradient(ellipse at top, rgba(255,255,255,.04), transparent);
}
.mode-card:hover::after { opacity: 1; }
.mode-card.safe    { background: linear-gradient(145deg,#04110d,#051410); border-color: rgba(0,229,160,.18); }
.mode-card.balanced{ background: linear-gradient(145deg,#040f1e,#060f1e); border-color: rgba(77,184,255,.18); }
.mode-card.risky   { background: linear-gradient(145deg,#130408,#170508); border-color: rgba(255,77,109,.18); }
.mode-card:hover { transform: translateY(-4px); box-shadow: var(--shadow); }
.mode-card.active.safe    { border-color: var(--grn); box-shadow: 0 0 40px rgba(0,229,160,.12); }
.mode-card.active.balanced{ border-color: var(--blu); box-shadow: 0 0 40px rgba(77,184,255,.12); }
.mode-card.active.risky   { border-color: var(--red); box-shadow: 0 0 40px rgba(255,77,109,.12); }
.mode-icon { font-size: 2rem; margin-bottom: 9px; }
.mode-name {
  font-family: 'Barlow Condensed', sans-serif; font-size: 1.3rem; font-weight: 800; letter-spacing: 2px;
}
.mode-card.safe     .mode-name { color: var(--grn); }
.mode-card.balanced .mode-name { color: var(--blu); }
.mode-card.risky    .mode-name { color: var(--red); }
.mode-desc { font-size: .7rem; color: var(--txt3); margin-top: 5px; line-height: 1.5; }
.mode-note {
  font-size: .62rem; margin-top: 8px; padding: 3px 10px; border-radius: 6px;
  display: inline-block; font-weight: 700; letter-spacing: .5px;
}
.mode-card.safe     .mode-note { background: rgba(0,229,160,.1);   color: var(--grn); }
.mode-card.balanced .mode-note { background: rgba(77,184,255,.1);  color: var(--blu); }
.mode-card.risky    .mode-note { background: rgba(255,77,109,.1);  color: var(--red); }

.adv-section {
  background: var(--s2); border: 1px solid var(--brd); border-radius: var(--r);
  overflow: hidden; margin-bottom: 24px;
}
.adv-header {
  background: var(--s1); border-bottom: 1px solid var(--brd);
  padding: 14px 20px; display: flex; align-items: center; justify-content: space-between;
  cursor: pointer; user-select: none;
}
.adv-header-title { font-family: 'Barlow Condensed', sans-serif; font-size: .9rem; font-weight: 700; letter-spacing: 1.5px; color: var(--txt); }
.adv-header-arrow { color: var(--gld); transition: transform .25s; font-size: 1.1rem; }
.adv-header-arrow.open { transform: rotate(180deg); }
.adv-body { padding: 20px; }

.adv-group { margin-bottom: 22px; }
.adv-group:last-child { margin-bottom: 0; }
.adv-group-title {
  font-family: 'Barlow Condensed', sans-serif; font-size: .72rem; font-weight: 700; letter-spacing: 2px;
  color: var(--txt3); text-transform: uppercase; margin-bottom: 12px;
  padding-bottom: 7px; border-bottom: 1px solid var(--brd);
  display: flex; align-items: center; gap: 8px;
}
.adv-group-title span { background: var(--s3); border: 1px solid var(--brd2); border-radius: 5px; padding: 1px 8px; font-size: .6rem; color: var(--gld); letter-spacing: .8px; }

.crit-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(248px, 1fr)); gap: 7px; }
.crit-item {
  background: var(--s3); border: 1px solid var(--brd); border-radius: var(--r3);
  padding: 9px 13px; display: flex; align-items: flex-start; gap: 10px;
  cursor: pointer; transition: border-color .16s, background .16s; user-select: none;
}
.crit-item:hover { border-color: rgba(245,200,66,.35); background: var(--s4); }
.crit-item:has(input:checked) { border-color: rgba(245,200,66,.4); background: var(--gld-dim); }
.crit-item input[type="checkbox"] { accent-color: var(--gld); width: 15px; height: 15px; flex-shrink: 0; cursor: pointer; margin-top: 2px; }
.crit-label { font-size: .73rem; color: var(--txt); cursor: pointer; line-height: 1.4; }
.crit-label small { display: block; color: var(--txt3); font-size: .62rem; margin-top: 1px; }

.slider-group { display: flex; flex-direction: column; gap: 6px; }
.slider-group label { font-size: .65rem; color: var(--txt3); letter-spacing: 1px; text-transform: uppercase; font-weight: 600; display: flex; justify-content: space-between; align-items: center; }
.slider-group label span { color: var(--gld); font-weight: 700; font-size: .72rem; }
input[type="range"] { width: 100%; accent-color: var(--gld); height: 4px; cursor: pointer; }

.input-row { display: flex; gap: 13px; flex-wrap: wrap; margin-bottom: 18px; }
.input-group { flex: 1; min-width: 130px; display: flex; flex-direction: column; gap: 6px; }
.input-group label { font-size: .63rem; color: var(--txt3); letter-spacing: 1px; text-transform: uppercase; font-weight: 600; }
.input-group input, .input-group select {
  background: var(--s3); border: 1px solid var(--brd); border-radius: var(--r3);
  padding: 9px 12px; color: var(--txt); font-size: .83rem;
  font-family: 'DM Sans', sans-serif; width: 100%; transition: border-color .18s; outline: none;
}
.input-group input:focus, .input-group select:focus { border-color: rgba(245,200,66,.5); box-shadow: 0 0 0 3px rgba(245,200,66,.07); }

.btn {
  display: inline-flex; align-items: center; justify-content: center; gap: 8px;
  padding: 10px 24px; border-radius: var(--r3); border: none; cursor: pointer;
  font-family: 'Barlow Condensed', sans-serif; font-size: 1rem; font-weight: 700; letter-spacing: 1px;
  text-decoration: none; transition: all .22s; white-space: nowrap;
  position: relative; overflow: hidden;
}
.btn::after { content: ''; position: absolute; inset: 0; opacity: 0; background: rgba(255,255,255,.08); transition: opacity .2s; }
.btn:hover::after { opacity: 1; }
.btn-gold { background: linear-gradient(135deg, var(--gld3), var(--gld), var(--gld2)); color: #000; box-shadow: 0 4px 18px rgba(245,200,66,.22); }
.btn-gold:hover { transform: translateY(-2px); box-shadow: 0 8px 28px rgba(245,200,66,.3); }
.btn-ora { background: linear-gradient(135deg,#ff7043,#d43200); color: #fff; box-shadow: 0 4px 18px rgba(255,112,67,.25); }
.btn-ora:hover { transform: translateY(-2px); box-shadow: 0 8px 28px rgba(255,112,67,.35); }
.btn-grn { background: linear-gradient(135deg,var(--grn),#00b87a); color: #000; box-shadow: 0 4px 18px rgba(0,229,160,.2); }
.btn-grn:hover { transform: translateY(-2px); box-shadow: 0 8px 28px rgba(0,229,160,.3); }
.btn-ghost { background: transparent; color: var(--txt3); border: 1px solid var(--brd); }
.btn-ghost:hover { border-color: var(--brd3); color: var(--txt); }
.btn-row { display: flex; gap: 11px; flex-wrap: wrap; margin-bottom: 30px; align-items: center; }
.btn-lg { padding: 14px 32px; font-size: 1.1rem; border-radius: 11px; letter-spacing: 1.5px; }
.btn-xl { padding: 16px 40px; font-size: 1.2rem; border-radius: 12px; letter-spacing: 2px; }

.alert-sel {
  background: rgba(245,200,66,.06); border: 1px solid rgba(245,200,66,.2);
  border-radius: var(--r3); padding: 10px 14px; font-size: .8rem; color: var(--txt2);
  margin-bottom: 16px; display: none; line-height: 1.5;
}

.divider { height: 1px; background: var(--brd); margin: 26px 0; }

.match-strip {
  background: var(--s2); border: 1px solid var(--brd); border-radius: var(--r);
  padding: 16px 22px; margin-bottom: 20px;
  display: flex; align-items: center; gap: 16px; flex-wrap: wrap;
}
.strip-vs { font-family: 'Barlow Condensed', sans-serif; font-size: 1.5rem; font-weight: 800; letter-spacing: 1.5px; line-height: 1; }
.strip-vs em { color: var(--gld); font-style: normal; margin: 0 10px; font-size: .85rem; font-weight: 400; }
.strip-venue { font-size: .65rem; color: var(--txt3); margin-top: 3px; }
.strip-right { margin-left: auto; display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }
.pill { padding: 3px 12px; border-radius: 100px; font-size: .66rem; font-weight: 700; text-transform: uppercase; letter-spacing: .8px; border: 1px solid transparent; }
.pill-safe    { background: rgba(0,229,160,.1);  color: var(--grn); border-color: rgba(0,229,160,.2); }
.pill-balanced{ background: rgba(77,184,255,.1); color: var(--blu); border-color: rgba(77,184,255,.2); }
.pill-risky   { background: rgba(255,77,109,.1); color: var(--red); border-color: rgba(255,77,109,.2); }
.pill-neutral { background: var(--s3); color: var(--txt3); border-color: var(--brd); }

.stats-bar { display: flex; gap: 10px; flex-wrap: wrap; margin-bottom: 20px; }
.stat-chip { background: var(--s2); border: 1px solid var(--brd); border-radius: 11px; padding: 10px 18px; text-align: center; flex: 1; min-width: 80px; }
.stat-chip strong { display: block; font-family: 'Barlow Condensed',sans-serif; font-size: 1.1rem; font-weight: 800; color: var(--gld); line-height: 1; }
.stat-chip span   { font-size: .6rem; color: var(--txt3); text-transform: uppercase; letter-spacing: .5px; margin-top: 2px; display: block; }

.res-topbar { display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 12px; margin-bottom: 18px; }
.team-grid  { display: grid; grid-template-columns: repeat(auto-fill, minmax(295px, 1fr)); gap: 14px; }

.team-card {
  background: var(--s2); border: 1px solid var(--brd); border-radius: var(--r);
  overflow: hidden; position: relative; transition: border-color .2s, transform .22s, box-shadow .22s;
  will-change: transform;
}
.team-card:hover { border-color: var(--brd3); transform: translateY(-2px); box-shadow: var(--shadow); }
.team-hdr {
  background: linear-gradient(135deg, var(--s3), var(--s1));
  padding: 11px 15px; display: flex; justify-content: space-between; align-items: center;
  border-bottom: 1px solid var(--brd);
}
.team-num { font-family: 'Barlow Condensed', sans-serif; font-size: .9rem; font-weight: 800; color: var(--gld); letter-spacing: 2px; }
.badge { font-size: .58rem; font-weight: 700; padding: 3px 9px; border-radius: 100px; letter-spacing: .8px; text-transform: uppercase; }
.badge-free { background: var(--grn); color: #000; }
.badge-lock { background: var(--s5); color: var(--txt3); border: 1px solid var(--brd2); }

.cv-row { display: flex; gap: 7px; padding: 11px 13px 0; }
.cv-pill { flex: 1; background: var(--s3); border: 1px solid var(--brd); border-radius: var(--r3); padding: 7px 9px; text-align: center; }
.cv-lbl  { display: block; font-size: .56rem; color: var(--txt3); letter-spacing: .4px; text-transform: uppercase; font-weight: 600; margin-bottom: 2px; }
.cv-nm   { font-size: .76rem; font-weight: 700; display: block; line-height: 1.25; }
.cv-c  .cv-nm { color: var(--gld); }
.cv-vc .cv-nm { color: var(--blu); }

.plist { list-style: none; padding: 9px 13px 0; }
.pitem { display: flex; align-items: center; gap: 7px; padding: 5px 0; border-bottom: 1px solid rgba(30,34,56,.8); font-size: .74rem; }
.pitem:last-child { border-bottom: none; }
.rdot { width: 5px; height: 5px; border-radius: 50%; flex-shrink: 0; }
.d-bat  { background: var(--blu); }
.d-bowl { background: var(--ora); }
.d-ar   { background: var(--grn); }
.d-wk   { background: var(--gld); }
.pname { flex: 1; color: var(--txt); }
.ct  { color: var(--gld); font-size: .6rem; font-weight: 800; margin-left: 3px; }
.vct { color: var(--blu); font-size: .6rem; font-weight: 800; margin-left: 3px; }
.rtag { font-size: .58rem; font-weight: 700; padding: 1px 6px; border-radius: 5px; flex-shrink: 0; }
.rL { background: rgba(0,229,160,.1);   color: var(--grn); }
.rM { background: rgba(77,184,255,.1);  color: var(--blu); }
.rH { background: rgba(255,77,109,.1);  color: var(--red); }

.card-foot { padding: 9px 13px; border-top: 1px solid var(--brd); margin-top: 9px; display: flex; justify-content: space-between; align-items: center; }
.foot-info { font-size: .62rem; color: var(--txt3); }
.copy-btn {
  background: none; border: 1px solid var(--brd); color: var(--txt3);
  font-size: .67rem; padding: 4px 11px; border-radius: 6px; cursor: pointer;
  transition: all .18s; font-family: 'DM Sans', sans-serif; font-weight: 500;
}
.copy-btn:hover:not(:disabled) { border-color: var(--gld); color: var(--gld); }
.copy-btn:disabled { opacity: .22; cursor: default; }

.lock-ov {
  position: absolute; inset: 0; background: rgba(6,8,16,.88);
  backdrop-filter: blur(6px); -webkit-backdrop-filter: blur(6px);
  border-radius: var(--r); z-index: 20;
  display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 6px;
  transition: opacity .45s ease;
}
.lock-ico { font-size: 1.8rem; }
.lock-lbl { font-family: 'Barlow Condensed',sans-serif; font-size: .9rem; font-weight: 800; letter-spacing: 2px; color: var(--txt3); }
.lock-sub { font-size: .62rem; color: var(--txt3); }

.unlock-banner {
  grid-column: 1/-1;
  background: linear-gradient(135deg, rgba(20,15,2,.95), rgba(28,20,4,.95));
  border: 2px solid rgba(245,200,66,.3); border-radius: 16px;
  padding: 28px 32px; text-align: center; position: relative; overflow: hidden;
}
.unlock-banner::before {
  content: ''; position: absolute; inset: 0;
  background: radial-gradient(ellipse at top, rgba(245,200,66,.07), transparent 70%); pointer-events: none;
}
.unlock-count {
  display: inline-block; background: rgba(245,200,66,.12); border: 1px solid rgba(245,200,66,.28);
  border-radius: 100px; padding: 4px 16px; font-size: .68rem; color: var(--gld);
  font-weight: 700; letter-spacing: 1px; text-transform: uppercase; margin-bottom: 10px; position: relative;
}
.unlock-banner h3 { font-family: 'Barlow Condensed', sans-serif; font-size: 1.6rem; font-weight: 800; letter-spacing: 2px; color: var(--gld); margin-bottom: 6px; position: relative; }
.unlock-banner > p { color: var(--txt3); font-size: .8rem; margin-bottom: 18px; position: relative; line-height: 1.6; }
.unlock-banner .btn { position: relative; }
.unlock-perks { display: flex; justify-content: center; gap: 20px; flex-wrap: wrap; margin-bottom: 18px; position: relative; }
.unlock-perk { font-size: .7rem; color: var(--txt2); display: flex; align-items: center; gap: 5px; }

.modal-bg {
  position: fixed; inset: 0; background: rgba(0,0,0,.96); z-index: 9000;
  display: flex; align-items: center; justify-content: center;
  opacity: 0; pointer-events: none; transition: opacity .28s;
}
.modal-bg.open { opacity: 1; pointer-events: all; }
.modal-box {
  background: var(--s2); border: 2px solid rgba(245,200,66,.3); border-radius: 18px;
  padding: 36px 40px; max-width: 420px; width: 94%; text-align: center;
  transform: scale(.94) translateY(16px); transition: transform .28s cubic-bezier(.34,1.56,.64,1);
  position: relative; overflow: hidden;
}
.modal-box::before { content: ''; position: absolute; top: 0; left: 0; right: 0; height: 3px; background: linear-gradient(90deg, var(--gld), var(--ora), var(--gld)); }
.modal-bg.open .modal-box { transform: scale(1) translateY(0); }
.modal-box h2 { font-family: 'Barlow Condensed', sans-serif; font-size: 1.65rem; font-weight: 800; letter-spacing: 2px; color: var(--gld); margin-bottom: 6px; }
.modal-box > p { color: var(--txt3); font-size: .8rem; margin-bottom: 18px; line-height: 1.6; }
.ad-box { background: var(--s1); border: 2px dashed var(--brd2); border-radius: 13px; padding: 24px 20px; margin: 0 0 16px; }
.ad-icon { font-size: 2.6rem; margin-bottom: 8px; }
.ad-label { font-size: .85rem; color: var(--txt2); font-weight: 600; }
.ad-sub { font-size: .68rem; color: var(--txt3); margin-top: 3px; }
.ad-prog { height: 7px; background: var(--brd); border-radius: 100px; overflow: hidden; margin-top: 16px; }
.ad-bar { height: 100%; border-radius: 100px; width: 0%; background: linear-gradient(90deg, var(--ora), var(--gld)); transition: width .15s linear; box-shadow: 0 0 8px rgba(245,200,66,.4); }
.ad-tmr { font-family: 'Barlow Condensed',sans-serif; font-size: 1.15rem; font-weight: 800; color: var(--ora); margin-top: 11px; letter-spacing: 1.5px; }
.modal-close-note { font-size: .67rem; color: var(--txt3); margin-top: 10px; }

.toast {
  position: fixed; bottom: 24px; right: 24px; z-index: 9999;
  padding: 11px 20px; border-radius: 11px; font-size: .8rem; font-weight: 600;
  transform: translateY(56px); opacity: 0; transition: all .3s cubic-bezier(.34,1.56,.64,1);
  pointer-events: none; box-shadow: var(--shadow); max-width: 300px;
}
.toast.show { transform: translateY(0); opacity: 1; }

.spinner-overlay {
  position: fixed; inset: 0; background: rgba(6,8,16,.95); z-index: 8000;
  display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 20px;
  opacity: 0; pointer-events: none; transition: opacity .25s;
}
.spinner-overlay.active { opacity: 1; pointer-events: all; }
.spinner { width: 54px; height: 54px; border: 4px solid var(--brd2); border-top-color: var(--gld); border-radius: 50%; animation: spin .85s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }
.spinner-text { font-family: 'Barlow Condensed',sans-serif; font-size: 1.35rem; font-weight: 800; letter-spacing: 2px; color: var(--gld); }
.spinner-sub { font-size: .76rem; color: var(--txt3); }

.content-section { max-width: 860px; margin: 52px auto 0; padding: 0 20px; }
.content-section h2 { font-family: 'Barlow Condensed', sans-serif; font-size: 1.5rem; font-weight: 800; letter-spacing: 2px; color: var(--gld); margin-bottom: 14px; margin-top: 36px; }
.content-section h2:first-child { margin-top: 0; }
.content-section h3 { font-family: 'Barlow Condensed', sans-serif; font-size: 1.05rem; font-weight: 700; letter-spacing: 1px; color: var(--txt); margin: 20px 0 8px; }
.content-section p  { color: var(--txt2); font-size: .88rem; line-height: 1.75; margin-bottom: 12px; }
.content-section ul, .content-section ol { color: var(--txt2); font-size: .88rem; line-height: 1.75; padding-left: 1.5em; margin-bottom: 12px; }
.content-section li { margin-bottom: 5px; }
.content-section a  { color: var(--gld); text-decoration: none; }
.content-section a:hover { text-decoration: underline; }
.content-divider { height: 1px; background: var(--brd); margin: 30px 0; }

.strategy-grid { display: grid; grid-template-columns: repeat(3,1fr); gap: 12px; margin: 16px 0 24px; }
@media(max-width:580px) { .strategy-grid { grid-template-columns:1fr; } }
.strategy-card { background: var(--s2); border: 1px solid var(--brd); border-radius: var(--r); padding: 18px 16px; }
.strategy-card h4 { font-family:'Barlow Condensed',sans-serif; font-size:.9rem; font-weight:800; margin-bottom:7px; letter-spacing:1px; }
.strategy-card p  { font-size:.75rem; color:var(--txt3); line-height:1.55; margin:0; }
.strat-safe    { border-top: 3px solid var(--grn); }
.strat-safe    h4 { color: var(--grn); }
.strat-balanced{ border-top: 3px solid var(--blu); }
.strat-balanced h4{ color: var(--blu); }
.strat-risky   { border-top: 3px solid var(--red); }
.strat-risky   h4 { color: var(--red); }

.tips-box { background: rgba(0,229,160,.05); border: 1px solid rgba(0,229,160,.15); border-radius: var(--r); padding: 18px 20px; margin: 20px 0; }
.tips-box h4 { font-family:'Barlow Condensed',sans-serif; color:var(--grn); font-size:.9rem; letter-spacing:1px; margin-bottom:10px; }
.tips-box ul { color: var(--txt2); font-size:.83rem; margin:0; }

.faq-item { background: var(--s2); border: 1px solid var(--brd); border-radius: 11px; margin-bottom: 8px; overflow: hidden; }
.faq-q { padding: 14px 17px; cursor: pointer; font-size: .85rem; font-weight: 600; color: var(--txt); display: flex; justify-content: space-between; align-items: center; transition: background .18s; gap: 12px; }
.faq-q:hover { background: var(--s3); }
.faq-q .arrow { color: var(--gld); font-size: 1rem; transition: transform .22s; flex-shrink: 0; }
.faq-q.open .arrow { transform: rotate(180deg); }
.faq-a { padding: 0 17px; max-height: 0; overflow: hidden; transition: max-height .32s ease, padding .32s; font-size: .82rem; color: var(--txt2); line-height: 1.7; }
.faq-a.open { max-height: 400px; padding: 0 17px 15px; }

footer { background: var(--s1); border-top: 1px solid var(--brd); padding: 36px 28px 24px; margin-top: 64px; }
.footer-grid { max-width: 1200px; margin: 0 auto; display: grid; grid-template-columns: repeat(auto-fit, minmax(200px,1fr)); gap: 28px; margin-bottom: 26px; }
.footer-col h4 { font-family: 'Barlow Condensed', sans-serif; font-size: .9rem; font-weight: 800; letter-spacing: 1.5px; color: var(--gld); margin-bottom: 10px; }
.footer-col p, .footer-col a { font-size: .74rem; color: var(--txt3); display: block; margin-bottom: 5px; text-decoration: none; transition: color .18s; line-height: 1.6; }
.footer-col a:hover { color: var(--txt); }
.footer-bottom { max-width: 1200px; margin: 0 auto; padding-top: 18px; border-top: 1px solid var(--brd); display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 10px; }
.footer-bottom p { font-size: .68rem; color: var(--txt3); }
.footer-disclaimer { font-size: .67rem; color: var(--txt3); line-height: 1.6; max-width: 1200px; margin: 16px auto 0; text-align: center; }
.footer-trust { display: flex; gap: 12px; flex-wrap: wrap; justify-content: center; margin-bottom: 16px; }
.trust-badge { background: var(--s2); border: 1px solid var(--brd); border-radius: 8px; padding: 5px 13px; font-size: .65rem; color: var(--txt3); letter-spacing: .5px; }

.legal-wrap { max-width: 820px; margin: 0 auto; padding: 42px 22px 90px; }
.legal-wrap h1 { font-family: 'Barlow Condensed', sans-serif; font-size: 2rem; font-weight: 800; letter-spacing: 3px; color: var(--gld); margin-bottom: 6px; }
.legal-wrap .last-updated { font-size: .7rem; color: var(--txt3); margin-bottom: 28px; }
.legal-wrap h2 { font-family:'Barlow Condensed',sans-serif; font-size: 1.05rem; font-weight: 700; color: var(--txt); margin: 24px 0 8px; }
.legal-wrap p  { font-size: .85rem; color: var(--txt2); line-height: 1.75; margin-bottom: 12px; }
.legal-wrap ul { font-size: .85rem; color: var(--txt2); line-height: 1.75; padding-left: 1.5em; margin-bottom: 12px; }
.legal-wrap li { margin-bottom: 4px; }
.legal-wrap a  { color: var(--gld); text-decoration: none; }

.contact-form { display: flex; flex-direction: column; gap: 15px; max-width: 560px; }
.form-group   { display: flex; flex-direction: column; gap: 6px; }
.form-group label { font-size: .7rem; color: var(--txt3); letter-spacing: 1px; text-transform: uppercase; font-weight: 600; }
.form-group input, .form-group textarea, .form-group select {
  background: var(--s2); border: 1px solid var(--brd); border-radius: var(--r3);
  padding: 10px 13px; color: var(--txt); font-size: .85rem; font-family: 'DM Sans', sans-serif;
  outline: none; transition: border-color .18s;
}
.form-group input:focus, .form-group textarea:focus { border-color: rgba(245,200,66,.5); box-shadow: 0 0 0 3px rgba(245,200,66,.07); }
.form-group textarea { resize: vertical; min-height: 120px; }
.form-msg { background: rgba(0,229,160,.08); border: 1px solid rgba(0,229,160,.25); border-radius: var(--r3); padding: 13px 16px; font-size: .82rem; color: var(--grn); display: none; }

.about-grid { display: grid; grid-template-columns: repeat(auto-fill,minmax(220px,1fr)); gap: 13px; margin: 20px 0; }
.about-card { background: var(--s2); border: 1px solid var(--brd); border-radius: var(--r); padding: 22px 18px; text-align: center; }
.about-icon  { font-size: 2.1rem; margin-bottom: 10px; }
.about-card h3 { font-family:'Barlow Condensed',sans-serif; font-size: .9rem; font-weight: 800; color: var(--txt); margin-bottom: 6px; }
.about-card p  { font-size: .74rem; color: var(--txt3); line-height: 1.55; }

.success-banner {
  background: linear-gradient(135deg, rgba(0,229,160,.08), rgba(0,229,160,.04));
  border-bottom: 1px solid rgba(0,229,160,.18);
  padding: 12px 28px; display: flex; align-items: center; gap: 14px;
  font-size: .82rem; color: var(--txt2);
}
.success-banner strong { color: var(--grn); display: block; font-size: .88rem; margin-bottom: 1px; }
.success-sub { font-size: .73rem; color: var(--txt3); }

@keyframes fadeUp { from { opacity: 0; transform: translateY(16px); } to { opacity: 1; transform: translateY(0); } }
.fade-up { animation: fadeUp .38s ease both; }

.skip-link {
  position: absolute; top: -50px; left: 18px; z-index: 9999;
  background: var(--gld); color: #000; padding: 8px 18px;
  border-radius: 0 0 9px 9px; font-size: .82rem; font-weight: 700;
  text-decoration: none; transition: top .2s;
}
.skip-link:focus { top: 0; }
:focus-visible { outline: 2px solid var(--gld); outline-offset: 2px; border-radius: 4px; }
button:focus-visible, a:focus-visible { outline: 2px solid var(--gld); outline-offset: 3px; }

.chip-picker { background: var(--s3); border: 1px solid var(--brd); border-radius: var(--r3); padding: 12px; min-height: 90px; }
.chip-placeholder { font-size: .73rem; color: var(--txt3); font-style: italic; }
.chip-team-lbl { font-size: .6rem; font-weight: 700; color: var(--txt3); letter-spacing: 1.2px; text-transform: uppercase; margin: 10px 0 6px; }
.chip-team-lbl:first-child { margin-top: 0; }
.chip-row { display: flex; flex-wrap: wrap; gap: 5px; margin-bottom: 4px; }
.pchip {
  display: inline-flex; align-items: center; gap: 6px;
  background: var(--s4); border: 1px solid var(--brd2); border-radius: 7px;
  padding: 5px 11px; cursor: pointer; transition: all .16s;
  font-family: 'DM Sans', sans-serif; user-select: none;
}
.pchip:hover { border-color: rgba(245,200,66,.5); background: var(--gld-dim); }
.pchip--active { background: var(--gld-dim); border-color: var(--gld); box-shadow: 0 0 0 1px var(--gld); }
.pchip--active-excl { background: rgba(255,77,109,.12); border-color: var(--red); box-shadow: 0 0 0 1px var(--red); }
.pchip-name { font-size: .73rem; color: var(--txt); font-weight: 500; line-height: 1; }
.pchip-role { font-size: .58rem; color: var(--txt3); background: var(--s1); border-radius: 4px; padding: 1px 6px; }
.pchip--active .pchip-name { color: var(--gld); }
.pchip--active .pchip-role { color: var(--gld); background: rgba(245,200,66,.1); }
.pchip--active-excl .pchip-name { color: var(--red); }
.pchip--active-excl .pchip-role { color: var(--red); background: rgba(255,77,109,.1); }
.chip-summary { font-size: .7rem; margin-top: 8px; min-height: 18px; line-height: 1.5; }

.age-gate-overlay {
  position: fixed; inset: 0; z-index: 99999;
  background: rgba(4,5,12,.97);
  backdrop-filter: blur(18px); -webkit-backdrop-filter: blur(18px);
  display: flex; align-items: center; justify-content: center; padding: 20px;
}
.age-gate-box {
  background: var(--s2); border: 1px solid var(--brd2); border-radius: 20px;
  padding: 44px 40px 36px; max-width: 420px; width: 100%; text-align: center;
  position: relative; overflow: hidden; box-shadow: 0 24px 80px rgba(0,0,0,.7);
  animation: fadeUp .35s ease both;
}
.age-gate-box::before { content: ''; position: absolute; top: 0; left: 0; right: 0; height: 3px; background: linear-gradient(90deg, var(--gld3), var(--gld), var(--ora)); }
.age-gate-badge {
  display: inline-flex; align-items: center; justify-content: center;
  width: 64px; height: 64px; border-radius: 50%;
  background: linear-gradient(135deg, rgba(245,200,66,.15), rgba(245,200,66,.05));
  border: 2px solid rgba(245,200,66,.3); font-size: 1.9rem; margin-bottom: 18px;
}
.age-gate-box h2 { font-family: 'Barlow Condensed', sans-serif; font-size: 1.75rem; font-weight: 800; letter-spacing: 2px; color: var(--txt); margin-bottom: 8px; }
.age-gate-box p { font-size: .85rem; color: var(--txt3); line-height: 1.65; margin-bottom: 28px; }
.age-gate-btn-row { display: flex; gap: 12px; justify-content: center; }
.age-gate-yes {
  flex: 1; padding: 14px 20px; border: none; border-radius: 11px; cursor: pointer;
  font-family: 'Barlow Condensed', sans-serif; font-size: 1.1rem; font-weight: 800;
  letter-spacing: 1.5px; transition: all .22s;
  background: linear-gradient(135deg, var(--gld3), var(--gld), var(--gld2));
  color: #000; box-shadow: 0 6px 22px rgba(245,200,66,.3);
}
.age-gate-yes:hover { transform: translateY(-2px); box-shadow: 0 10px 32px rgba(245,200,66,.45); }
.age-gate-no {
  padding: 14px 20px; border: 1px solid var(--brd2); border-radius: 11px; cursor: pointer;
  font-family: 'Barlow Condensed', sans-serif; font-size: 1rem; font-weight: 600;
  letter-spacing: 1px; transition: all .2s; background: transparent; color: var(--txt3); min-width: 90px;
}
.age-gate-no:hover { border-color: var(--red); color: var(--red); }
.age-gate-note { font-size: .65rem; color: var(--txt4); margin-top: 16px; line-height: 1.5; }
.age-gate-blocked {
  position: fixed; inset: 0; z-index: 99999; background: rgba(4,5,12,.99);
  display: none; align-items: center; justify-content: center;
  flex-direction: column; gap: 14px; text-align: center; padding: 28px;
}
.age-gate-blocked h3 { font-family: 'Barlow Condensed', sans-serif; font-size: 1.4rem; font-weight: 800; letter-spacing: 2px; color: var(--red); }
.age-gate-blocked p { color: var(--txt3); font-size: .85rem; max-width: 340px; }

@media print {
  header,.step-bar,nav,.unlock-banner,.btn,.copy-btn,.lock-ov,.modal-bg,.toast,footer,.content-section,.tab-bar,.spinner-overlay { display:none!important; }
  body { background:#fff; color:#000; padding-top:0; }
  .team-card { border:1px solid #ccc; break-inside:avoid; background:#fff; }
  .team-hdr  { background:#f5f5f5; }
  .pname     { color:#000; }
  .cv-nm     { color:#b8860b!important; }
}

/* ── Mobile (≤ 768px) ── */
@media(max-width:768px) {
  :root { --hdr-h: 52px; --step-h: 44px; }
  body  { font-size: 14px; }
  header { padding: 0 14px; }
  .logo  { font-size: 1.05rem; letter-spacing: 1px; }
  .hdr-nav a:not(.cta) { display: none; }
  .hdr-nav a.cta { padding: 6px 13px; font-size: .82rem; }
  .step-bar { padding: 0 12px; }
  .step-lbl { display: none; }
  .step-line { margin: 0 4px; }
  .wrap  { padding: 14px 12px 60px; }
  .match-grid { grid-template-columns: 1fr; gap: 8px; }
  .match-vs   { font-size: 1.2rem; }
  .mode-grid  { grid-template-columns: 1fr; gap: 8px; }
  .mode-card  { padding: 16px 14px; }
  .mode-name  { font-size: 1.1rem; }
  .adv-body   { padding: 14px; }
  .input-row  { flex-direction: column; gap: 10px; }
  .crit-grid  { grid-template-columns: 1fr; }
  .team-grid  { grid-template-columns: 1fr; gap: 10px; }
  .modal-box  { padding: 22px 16px; margin: 0 10px; }
  .btn-xl     { padding: 13px 22px; font-size: 1rem; letter-spacing: 1px; }
  .btn-lg     { padding: 11px 22px; font-size: .95rem; }
  .btn-row    { flex-direction: column; gap: 8px; }
  .btn-row .btn { width: 100%; justify-content: center; }
  .stats-bar  { gap: 6px; }
  .stat-chip  { padding: 8px 10px; min-width: 60px; }
  .match-strip { padding: 12px 14px; flex-direction: column; gap: 10px; }
  .strip-right { margin-left: 0; }
  .strip-vs    { font-size: 1.2rem; }
  .cv-row      { flex-direction: column; gap: 5px; }
  .unlock-banner { padding: 20px 16px; }
  .unlock-banner h3 { font-size: 1.2rem; }
  .unlock-perks { gap: 10px; }
  .strategy-grid { grid-template-columns: 1fr; }
  .about-grid    { grid-template-columns: 1fr; }
  .footer-grid   { grid-template-columns: 1fr; gap: 18px; }
  .footer-bottom { flex-direction: column; text-align: center; gap: 4px; }
  .footer-trust  { gap: 6px; }
  .trust-badge   { font-size: .6rem; padding: 4px 9px; }
  .legal-wrap    { padding: 28px 14px 70px; }
  .legal-wrap h1 { font-size: 1.5rem; }
  .content-section { padding: 0 14px; }
  .adv-group-title { font-size: .65rem; }
  .age-gate-box { padding: 30px 20px 24px; }
  .age-gate-btn-row { flex-direction: column; gap: 8px; }
  .age-gate-yes, .age-gate-no { width: 100%; }
  .chip-picker  { padding: 10px; }
  .pchip        { padding: 4px 9px; }
  .pchip-name   { font-size: .68rem; }
  .tab-btn      { padding: 6px 12px; font-size: .75rem; }
  div[style*="grid-template-columns:1fr 1fr"] { display: grid !important; grid-template-columns: 1fr !important; gap: 12px !important; }
}

/* ── Small phones (≤ 380px) ── */
@media(max-width:380px) {
  .logo  { font-size: .92rem; }
  .btn-xl { padding: 12px 16px; font-size: .92rem; }
  .match-vs { font-size: 1.05rem; }
  .modal-box { padding: 18px 12px; }
}
</style>
<script async src="https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client=ca-pub-9904803540658016" crossorigin="anonymous"></script>
<script async src="https://www.googletagmanager.com/gtag/js?id=G-VJS4H89EKW"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){dataLayer.push(arguments);}
  gtag('js', new Date());
  gtag('config', 'G-VJS4H89EKW');
</script>
"""

# ─── Footer ───────────────────────────────────────────────────────────────────

_FOOTER = """
<footer>
  <div class="footer-grid z1">
    <div class="footer-col">
      <h4>⚡ AI Fantasy Team Generator</h4>
      <p>India's #1 <strong>AI Fantasy Team Generator</strong> for cricket. Generate 20 unique AI-powered Dream11 teams for IPL, T20 World Cup, ICC tournaments and all major cricket leagues — in seconds.</p>
      <p style="margin-top:9px;">📧 <a href="/contact">our contact form</a></p>
    </div>
    <div class="footer-col">
      <h4>Quick Links</h4>
      <a href="/">🏠 AI Team Generator</a>
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
      <p>This site uses cookies and may display third-party advertisements via Google AdSense. By using this site you agree to our <a href="/privacy">Privacy Policy</a> and <a href="/terms">Terms</a>.</p>
      <p style="margin-top:7px;">🔞 For users aged 18+ only.</p>
    </div>
  </div>
  <div class="footer-trust z1">
    <span class="trust-badge">🔒 Privacy First</span>
    <span class="trust-badge">🚫 No Login Required</span>
    <span class="trust-badge">⚡ Instant Generation</span>
    <span class="trust-badge">📊 Smart Algorithm</span>
  </div>
  <div class="footer-bottom z1">
    <p>© 2026 AI Fantasy Team Generator. All rights reserved. Not affiliated with ICC, BCCI, or any official cricket body.</p>
    <p>Built for entertainment &amp; informational purposes only.</p>
  </div>
  <div class="footer-disclaimer z1">
    ⚠️ Fantasy sports involve financial risk. Please play responsibly. AI Fantasy Team Generator does not guarantee any winnings. Check local laws before participating in paid fantasy sports contests. This tool is for users 18 years and above.
  </div>
</footer>
"""

# ─── Ad Modal ─────────────────────────────────────────────────────────────────

_AD_MODAL = """
<div class="modal-bg" id="adModal" aria-modal="true" role="dialog" aria-labelledby="adModalTitle">
  <div class="modal-box">
    <h2 id="adModalTitle">📺 Ad Experience</h2>
    <p>Watch this 5-second ad to instantly unlock all remaining teams — completely free.</p>
    <div class="ad-box">
      <div class="ad-icon">🎬</div>
      <div class="ad-label">Simulated Advertisement</div>
      <div class="ad-sub">No real Ad SDK · Safe &amp; compliant</div>
      <div class="ad-prog"><div class="ad-bar" id="adBar"></div></div>
      <div class="ad-tmr" id="adTmr">⏳ 5s remaining</div>
    </div>
    <p class="modal-close-note" id="closeNote">Please wait — your teams are almost ready…</p>
  </div>
</div>
<div class="toast" id="toast" role="status" aria-live="polite"></div>
"""

# ─── Shared JS ────────────────────────────────────────────────────────────────

_SHARED_JS = """
<script>
function showToast(msg, color) {
  color = color || '#00e5a0';
  var t = document.getElementById('toast');
  if (!t) return;
  t.textContent = msg; t.style.background = color;
  t.style.color = (color === '#00e5a0' || color === '#f5c842') ? '#000' : '#fff';
  t.classList.add('show');
  setTimeout(function(){ t.classList.remove('show'); }, 3400);
}

function scrollToId(id) {
  var el = document.getElementById(id);
  if (!el) return;
  var offset = 58 + 52 + 12;
  var y = el.getBoundingClientRect().top + window.pageYOffset - offset;
  window.scrollTo({ top: y, behavior: 'smooth' });
}

function toggleFaq(el) {
  var a = el.nextElementSibling;
  var isOpen = el.classList.contains('open');
  document.querySelectorAll('.faq-q').forEach(function(q) {
    q.classList.remove('open');
    if (q.nextElementSibling) q.nextElementSibling.classList.remove('open');
  });
  if (!isOpen) { el.classList.add('open'); if (a) a.classList.add('open'); }
}

var adInterval = null;
var adCountdown = 5;
var adRunning = false;

function openAd() {
  if (adRunning) return;
  var modal = document.getElementById('adModal');
  if (!modal) return;
  adCountdown = 5; adRunning = true;
  var bar  = document.getElementById('adBar');
  var tmr  = document.getElementById('adTmr');
  var note = document.getElementById('closeNote');
  if (bar)  bar.style.width = '0%';
  if (tmr)  tmr.textContent = '⏳ 5s remaining';
  if (note) note.textContent = 'Please wait — your teams are almost ready…';
  modal.classList.add('open');
  if (adInterval) { clearInterval(adInterval); adInterval = null; }
  adInterval = setInterval(function() {
    adCountdown--;
    var pct = ((5 - adCountdown) / 5 * 100).toFixed(1);
    if (bar) bar.style.width = pct + '%';
    if (adCountdown > 0) {
      if (tmr) tmr.textContent = '⏳ ' + adCountdown + 's remaining';
    } else {
      if (tmr)  tmr.textContent = '✅ Complete!';
      if (note) note.textContent = 'Unlocking your teams now…';
      clearInterval(adInterval); adInterval = null;
      setTimeout(function() {
        modal.classList.remove('open');
        adRunning = false;
        doUnlock();
      }, 700);
    }
  }, 1000);
}

function doUnlock() {
  fetch('/unlock', { method: 'POST', headers: { 'Content-Type': 'application/json' } })
    .then(function(r) { return r.json(); })
    .then(function(d) {
      if (!d.success) { showToast('Error unlocking. Please try again.', '#ff4d6d'); return; }
      document.querySelectorAll('.lock-ov').forEach(function(el) {
        el.style.opacity = '0';
        setTimeout(function() { if (el.parentNode) el.parentNode.removeChild(el); }, 480);
      });
      document.querySelectorAll('.copy-btn').forEach(function(b) { b.disabled = false; });
      document.querySelectorAll('.badge-lock').forEach(function(b) {
        b.textContent = '✓ UNLOCKED'; b.classList.remove('badge-lock'); b.classList.add('badge-free');
      });
      var banner = document.getElementById('unlockBanner');
      if (banner) {
        var total = document.querySelectorAll('.team-card').length;
        banner.innerHTML =
          '<div class="unlock-count" style="position:relative;">ALL ' + total + ' TEAMS UNLOCKED</div>'
          + '<h3 style="color:var(--grn);position:relative;">✅ Fully Unlocked!</h3>'
          + '<p style="position:relative;color:var(--txt2);">Enjoy all your generated teams. Download a clean PDF below.</p>'
          + '<div style="position:relative;margin-top:4px;">'
          + '<a href="/export_pdf" class="btn btn-grn btn-lg">📄 Export All as PDF</a></div>';
      }
      var pBtn = document.getElementById('pdfBtn');
      if (pBtn) pBtn.style.display = 'inline-flex';
      showToast('🎉 All teams unlocked! Enjoy.', '#f5c842');
    })
    .catch(function() { showToast('Network error. Please retry.', '#ff4d6d'); });
}

function copyTeam(idx) {
  var cards = document.querySelectorAll('.team-card');
  var card  = cards[idx];
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

# =============================================================================
# ─── HOME PAGE ───────────────────────────────────────────────────────────────
# =============================================================================

HOME_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<script async src="https://www.googletagmanager.com/gtag/js?id=G-VJS4H89EKW"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){dataLayer.push(arguments);}
  gtag('js', new Date());
  gtag('config', 'G-VJS4H89EKW');
</script>
<title>AI Fantasy Team Generator — AI 20 Fantasy Cricket Teams | Dream11, IPL, T20 World Cup</title>
<meta name="description" content="AI Fantasy Team Generator is the #1 AI Cricket Team Generator. Generate 20 unique Dream11 AI teams for IPL, T20 World Cup, ICC tournaments and all major leagues. Smart algorithm, Safe/Balanced/Risky modes — 100% free.">
<meta name="keywords" content="AI fantasy team generator, dream11 AI team, fantasy cricket AI, AI cricket team prediction, dream11 team generator, IPL fantasy team, T20 World Cup fantasy, ICC fantasy cricket, fantasy XI generator, AI fantasy cricket 2026">
<meta name="robots" content="index, follow">
<meta name="author" content="AI Fantasy Team Generator">
<meta property="og:title" content="AI Fantasy Team Generator — 20 AI Fantasy Cricket Teams | Dream11, IPL, T20 World Cup">
<meta property="og:description" content="Generate 20 unique AI-powered fantasy cricket teams for IPL, T20 World Cup, ICC tournaments and all major leagues. Safe, Balanced and Risky modes. 100% free.">
<meta property="og:type" content="website">
<meta property="og:url" content="https://fantasyxi.in/">
<meta property="og:site_name" content="AI Fantasy Team Generator">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="AI Fantasy Team Generator — 20 AI Fantasy Cricket Teams">
<meta name="twitter:description" content="Generate 20 unique AI-powered fantasy cricket teams for any match. Free Dream11 AI team generator with smart algorithm.">
<link rel="canonical" href="https://fantasyxi.in/">
<script type="application/ld+json">
{"@context":"https://schema.org","@type":"FAQPage","mainEntity":[
  {"@type":"Question","name":"What is AI Fantasy Team Generator?","acceptedAnswer":{"@type":"Answer","text":"AI Fantasy Team Generator is an AI-powered fantasy cricket team generator that creates 20 unique, optimised teams for any cricket match — IPL, T20 World Cup, ICC tournaments and all major leagues."}},
  {"@type":"Question","name":"Is the AI Fantasy Team Generator free to use?","acceptedAnswer":{"@type":"Answer","text":"Yes. The first 3 teams are always free. Remaining teams unlock by watching a 5-second simulated ad — no payment required."}},
  {"@type":"Question","name":"Which tournaments does the AI team generator support?","acceptedAnswer":{"@type":"Answer","text":"AI Fantasy Team Generator works for all major cricket tournaments including IPL, T20 World Cup, ICC Cricket World Cup, Big Bash League, The Hundred, and all international T20 series."}},
  {"@type":"Question","name":"How is this different from a normal fantasy team generator?","acceptedAnswer":{"@type":"Answer","text":"AI Fantasy Team Generator uses AI-powered risk weighting, intelligent C/VC rotation, exposure control, and differential injection — far beyond simple random generation."}},
  {"@type":"Question","name":"Are AI-generated fantasy teams guaranteed to win?","acceptedAnswer":{"@type":"Answer","text":"No. AI Fantasy Team Generator is an informational and entertainment tool. Outcomes depend on real match events. Always play responsibly."}}
]}</script>
<script type="application/ld+json">
{"@context":"https://schema.org","@type":"WebSite","name":"AI Fantasy Team Generator","url":"https://fantasyxi.in","description":"AI Fantasy Team Generator for cricket — IPL, T20 World Cup, ICC tournaments and all major leagues"}</script>
""" + _CSS + """
</head>
<body>

<div class="age-gate-overlay" id="ageGate" role="dialog" aria-modal="true" aria-labelledby="ageGateTitle">
  <div class="age-gate-box">
    <div class="age-gate-badge">🔞</div>
    <h2 id="ageGateTitle">Age Verification</h2>
    <p>AI Fantasy Team Generator contains content related to fantasy sports which may involve financial risk. You must be 18 years or older to continue.</p>
    <p style="font-weight:600;color:var(--txt);margin-bottom:28px;font-size:.9rem;">Are you 18 years or older?</p>
    <div class="age-gate-btn-row">
      <button class="age-gate-yes" onclick="ageConfirm(true)">✓ Yes, I'm 18+</button>
      <button class="age-gate-no"  onclick="ageConfirm(false)">No</button>
    </div>
    <p class="age-gate-note">By clicking "Yes, I'm 18+", you confirm you are of legal age to access this content in your jurisdiction.</p>
  </div>
</div>
<div class="age-gate-blocked" id="ageBlocked">
  <h3>Access Restricted</h3>
  <p>You must be 18 years or older to access AI Fantasy Team Generator. This site contains content related to fantasy sports which is intended for adults only.</p>
</div>

<a href="#tool" class="skip-link">Skip to generator</a>

<div class="spinner-overlay" id="spinnerOverlay" role="status" aria-live="polite">
  <div class="spinner" aria-hidden="true"></div>
  <div class="spinner-text">Generating Teams…</div>
  <div class="spinner-sub">Running smart distribution engine · Please wait</div>
</div>

<header role="banner">
  <div class="logo-wrap">
    <a href="/" class="logo">⚡ AI Fantasy Team Generator</a>
  </div>
  <nav class="hdr-nav" aria-label="Main navigation">
    <a href="/about">About</a>
    <a href="/how-it-works">How It Works</a>
    <a href="/privacy">Privacy</a>
  </nav>
</header>

<div class="step-bar" id="stepBar" aria-label="Progress steps">
  <div class="step-bar-inner">
    <div class="step" id="step1">
      <div class="step-num">1</div>
      <span class="step-lbl">Select Match</span>
      <div class="step-line"></div>
    </div>
    <div class="step" id="step2">
      <div class="step-num">2</div>
      <span class="step-lbl">Choose Mode</span>
      <div class="step-line"></div>
    </div>
    <div class="step" id="step3">
      <div class="step-num">3</div>
      <span class="step-lbl">Set Criteria</span>
      <div class="step-line"></div>
    </div>
    <div class="step" id="step4">
      <div class="step-num">4</div>
      <span class="step-lbl">Generate</span>
    </div>
  </div>
</div>

<main class="wrap z1" id="tool">

  <div class="tab-bar" role="tablist">
    <button class="tab-btn active" onclick="showTab('up',this)" role="tab" aria-selected="true" aria-controls="tab-up">📅 Upcoming Matches</button>
    <button class="tab-btn" onclick="showTab('man',this)" role="tab" aria-selected="false" aria-controls="tab-man">⚙ Manual Selection</button>
  </div>

  <div id="tab-up" role="tabpanel">
    <h2 class="sh">Select a Match <small>Step 1</small></h2>
    <div class="match-grid" role="list">
    {% for m in matches %}
      <div class="match-card" role="listitem" tabindex="0"
        onclick="selectMatch('{{m.match_id}}','{{m.team1}}','{{m.team2}}','{{m.date}}','{{m.venue|replace(\"'\",\"\")}}',this)"
        onkeydown="if(event.key==='Enter')selectMatch('{{m.match_id}}','{{m.team1}}','{{m.team2}}','{{m.date}}','{{m.venue|replace(\"'\",\"\")}}',this)">
        <div class="match-time">{{m.time}}</div>
        <div class="match-id-tag">📅 {{m.date}} · {{m.match_id}}</div>
        <div class="match-vs">{{m.team1}}<em>VS</em>{{m.team2}}</div>
        <div class="match-venue">📍 {{m.venue}}</div>
      </div>
    {% endfor %}
    </div>
    <div class="alert-sel" id="selInfo" role="status"></div>
  </div>

  <div id="tab-man" style="display:none;" role="tabpanel">
    <div class="sh">Manual Team Selection</div>
    <div class="input-row">
      <div class="input-group">
        <label for="mt1">Team 1</label>
        <select id="mt1">{% for t in all_teams %}<option value="{{t.team}}">{{t.team}}</option>{% endfor %}</select>
      </div>
      <div class="input-group">
        <label for="mt2">Team 2</label>
        <select id="mt2">{% for t in all_teams %}<option value="{{t.team}}"{% if loop.index==2 %} selected{% endif %}>{{t.team}}</option>{% endfor %}</select>
      </div>
    </div>
    <button class="btn btn-ghost" onclick="setManual()">Confirm Teams →</button>
  </div>

  <div class="divider"></div>

  <div id="section-mode">
    <h2 class="sh">AI Generation Mode <small>Step 2</small></h2>
    <div class="mode-grid" role="radiogroup" aria-label="Generation mode">
      <div class="mode-card safe" role="radio" aria-checked="false" tabindex="0"
        onclick="selectMode('safe',this)"
        onkeydown="if(event.key==='Enter'||event.key===' ')selectMode('safe',this)">
        <div class="mode-icon">🛡</div>
        <div class="mode-name">Safe</div>
        <div class="mode-desc">Low-risk captains · Consistent stable picks · Minimise variance</div>
        <div class="mode-note">✓ Best for small contests &amp; H2H</div>
      </div>
      <div class="mode-card balanced" role="radio" aria-checked="false" tabindex="0"
        onclick="selectMode('balanced',this)"
        onkeydown="if(event.key==='Enter'||event.key===' ')selectMode('balanced',this)">
        <div class="mode-icon">⚖️</div>
        <div class="mode-name">Balanced</div>
        <div class="mode-desc">Mixed risk · Smart C/VC rotation · Best of both worlds</div>
        <div class="mode-note">✓ Best for mid-size contests</div>
      </div>
      <div class="mode-card risky" role="radio" aria-checked="false" tabindex="0"
        onclick="selectMode('risky',this)"
        onkeydown="if(event.key==='Enter'||event.key===' ')selectMode('risky',this)">
        <div class="mode-icon">🔥</div>
        <div class="mode-name">Risky</div>
        <div class="mode-desc">High-risk differentials · Max points ceiling · Stand out from the field</div>
        <div class="mode-note">✓ Best for mega contests</div>
      </div>
    </div>
  </div>

  <!-- ── Generate buttons: between Step 2 and Step 3 ── -->
  <div class="btn-row" id="generateBtnRow" style="margin-top:6px;margin-bottom:10px;">
    <button class="btn btn-gold btn-xl" id="generateBtn" onclick="doGenerate()" aria-label="Generate AI fantasy teams">
      🤖 Generate AI Teams
    </button>
    <button class="btn btn-ghost" onclick="resetAll()" aria-label="Reset all">↺ Reset All</button>
  </div>

  <div id="section-criteria">
    <h2 class="sh">Advanced Criteria <small>Step 3 · Optional</small></h2>

    <div class="adv-section">
      <div class="adv-header" onclick="toggleAdv(this)" role="button" aria-expanded="true" aria-controls="advBody">
        <span class="adv-header-title">⚙️ Configuration Engine — Power Options</span>
        <span class="adv-header-arrow open">▼</span>
      </div>

      <div class="adv-body" id="advBody">

        <div class="adv-group">
          <div class="adv-group-title">⚙️ Generation Settings <span>CORE</span></div>
          <div class="input-row">
            <div class="input-group">
              <label for="nt">Teams to Generate (max 20)</label>
              <input type="number" id="nt" value="20" min="5" max="20">
            </div>
            <div class="input-group">
              <label for="max_from_one">Max Players from One Team</label>
              <input type="number" id="max_from_one" value="7" min="5" max="10">
            </div>
          </div>
          <div class="input-row">
            <div class="input-group">
              <label for="exposure">Exposure Limit (%) <span style="color:var(--gld);font-weight:700;" id="exposureVal">75%</span></label>
              <input type="range" id="exposure" value="75" min="10" max="100" oninput="document.getElementById('exposureVal').textContent=this.value+'%'">
            </div>
            <div class="input-group">
              <label for="risk_intensity">Risk Intensity <span style="color:var(--gld);font-weight:700;" id="riskIntVal">1.0×</span></label>
              <input type="range" id="risk_intensity" value="10" min="5" max="25" oninput="document.getElementById('riskIntVal').textContent=(this.value/10).toFixed(1)+'×'">
            </div>
            <div class="input-group">
              <label for="rand_strength">Randomisation Strength <span style="color:var(--gld);font-weight:700;" id="randVal">Medium</span></label>
              <input type="range" id="rand_strength" value="5" min="0" max="10" oninput="document.getElementById('randVal').textContent=['Off','Very Low','Low','Low-Med','Medium','Medium','Med-High','High','High','Very High','Max'][this.value]">
            </div>
          </div>
        </div>

        <div class="adv-group">
          <div class="adv-group-title">👑 Captain &amp; Vice-Captain Rules <span>STRATEGY</span></div>
          <div class="crit-grid">
            <label class="crit-item"><input type="checkbox" id="c6" checked><div class="crit-label">At least 5 unique C/VC combinations<small>Ensures diversity across teams</small></div></label>
            <label class="crit-item"><input type="checkbox" id="c7" checked><div class="crit-label">Avoid same C/VC pair repeating<small>No duplicate captain combos</small></div></label>
            <label class="crit-item"><input type="checkbox" id="c8" checked><div class="crit-label">Risk-based captain weighting<small>Mode affects captain pool</small></div></label>
            <label class="crit-item"><input type="checkbox" id="c11" checked><div class="crit-label">Prevent same captain &gt;3 consecutive<small>Rotates captain intelligently</small></div></label>
            <label class="crit-item"><input type="checkbox" id="c15" checked><div class="crit-label">≥1 All-rounder captain in first 5<small>Guaranteed AR captaincy early</small></div></label>
            <label class="crit-item"><input type="checkbox" id="unique_cap"><div class="crit-label">Unique captain per team<small>No captain repeats across teams</small></div></label>
            <label class="crit-item"><input type="checkbox" id="unique_vc"><div class="crit-label">Unique vice-captain per team<small>No VC repeats across teams</small></div></label>
          </div>
        </div>

        <div class="adv-group">
          <div class="adv-group-title">🏏 Team Composition &amp; Distribution <span>STRUCTURE</span></div>
          <div class="crit-grid">
            <label class="crit-item"><input type="checkbox" id="c1" checked><div class="crit-label">6:5 team-split rotation<small>Alternates which team has 6 players</small></div></label>
            <label class="crit-item"><input type="checkbox" id="c12" checked><div class="crit-label">No identical team combination<small>Guarantees 100% unique teams</small></div></label>
            <label class="crit-item"><input type="checkbox" id="c13" checked><div class="crit-label">Max players from one team enforced<small>Uses "Max from One Team" setting</small></div></label>
            <label class="crit-item"><input type="checkbox" id="c14" checked><div class="crit-label">Role constraints (WK/BAT/AR/BOWL)<small>Valid fantasy composition required</small></div></label>
            <label class="crit-item"><input type="checkbox" id="balanced_dist"><div class="crit-label">Balanced distribution toggle<small>Equal player spread across teams</small></div></label>
            <label class="crit-item"><input type="checkbox" id="differential"><div class="crit-label">Differential injection (last 10 teams)<small>Boosts low-ownership players late</small></div></label>
          </div>
          <div class="input-row" style="margin-top:14px;margin-bottom:0;">
            <div class="input-group">
              <label for="min_diff">Min Differential Players per Team</label>
              <input type="number" id="min_diff" value="0" min="0" max="5">
            </div>
          </div>
        </div>

        <div class="adv-group">
          <div class="adv-group-title">🎯 Player Controls — Lock &amp; Exclude <span>PRECISION</span></div>
          <p style="font-size:.72rem;color:var(--txt3);margin-bottom:14px;">
            Select a match first to load players. <strong style="color:var(--txt2);">Click a chip to toggle</strong> lock (green) or exclude (red).
          </p>
          <div style="display:grid;grid-template-columns:1fr 1fr;gap:18px;">
            <div>
              <div style="font-size:.68rem;font-weight:700;color:var(--grn);letter-spacing:.9px;text-transform:uppercase;margin-bottom:8px;">
                🔒 Lock Players <span style="color:var(--txt3);font-weight:400;">(appear in every team)</span>
              </div>
              <div id="lock_picker" class="chip-picker"><span class="chip-placeholder">Select a match first</span></div>
              <div id="lock_summary" class="chip-summary"></div>
            </div>
            <div>
              <div style="font-size:.68rem;font-weight:700;color:var(--red);letter-spacing:.9px;text-transform:uppercase;margin-bottom:8px;">
                🚫 Exclude Players <span style="color:var(--txt3);font-weight:400;">(never picked)</span>
              </div>
              <div id="excl_picker" class="chip-picker"><span class="chip-placeholder">Select a match first</span></div>
              <div id="excl_summary" class="chip-summary"></div>
            </div>
          </div>
        </div>

      </div>
    </div>

  </div>

</main>

<section class="content-section z1" aria-label="Guide and FAQ" id="guide">

  <h2 id="how-it-works">What is AI Fantasy Team Generator?</h2>
  <p>AI Fantasy Team Generator is an <strong>AI-powered fantasy cricket team generator</strong> that builds 20 unique, strategically optimised Dream11 teams for any cricket match — IPL, ICC T20 World Cup, ODI World Cup, Big Bash League, The Hundred, international T20 series, and all other major cricket tournaments.</p>
  <p>Unlike basic random fantasy team builders, AI Fantasy Team Generator's engine applies multi-layer probability weighting, enforces cricket-valid role constraints, intelligently rotates captain and vice-captain selections, controls player exposure limits, and guarantees zero duplicate teams.</p>

  <h3>How the AI Team Generation Algorithm Works</h3>
  <p>Our AI fantasy team generator runs a sophisticated distribution engine behind the scenes. For each of the 20 team slots, the algorithm samples players using risk-weighted probabilities that reflect each player's expected impact and consistency. It tracks how many times each player has appeared across already-generated teams and actively reduces the probability of over-used players — keeping your ownership percentages healthy and your portfolio diverse.</p>

  <div class="content-divider"></div>

  <h2 id="strategy">AI Dream11 Team Strategy — Safe vs Balanced vs Risky</h2>
  <div class="strategy-grid">
    <div class="strategy-card strat-safe">
      <h4>🛡 Safe Mode</h4>
      <p>The AI weights low-risk players 5× above average and restricts captain selection to the most consistent performers. Ideal for small leagues and head-to-head contests.</p>
    </div>
    <div class="strategy-card strat-balanced">
      <h4>⚖️ Balanced Mode</h4>
      <p>The AI mixes low and medium risk with smart C/VC rotation. Best for mid-size contests (1,000–50,000 players).</p>
    </div>
    <div class="strategy-card strat-risky">
      <h4>🔥 Risky Mode</h4>
      <p>The AI heavily weights differential players (6× vs Low risk). Designed for mega contests and grand leagues (50,000+ players).</p>
    </div>
  </div>

  <div class="tips-box">
    <h4>💡 AI Fantasy Team Generator — Expert Tips</h4>
    <ul>
      <li>Use the <strong>exposure limit slider</strong> (75% default) so no single player dominates your 20-team portfolio.</li>
      <li>Enable <strong>differential injection</strong> in the AI — your last 10 teams will automatically favour lower-ownership picks.</li>
      <li>Lock your must-have players to guarantee they appear in every AI-generated team.</li>
      <li>In <strong>Risky mode</strong>, enable <strong>unique captain per team</strong> to spread AI captain picks across multiple differentials.</li>
      <li>For IPL grand leagues, use Risky mode with high randomisation strength for maximum portfolio diversity.</li>
    </ul>
  </div>

  <div class="content-divider"></div>

  <h2 id="faq">Frequently Asked Questions</h2>

  <div class="faq-item">
    <div class="faq-q" onclick="toggleFaq(this)">What is an AI Fantasy Team Generator? <span class="arrow">▼</span></div>
    <div class="faq-a">An AI Fantasy Team Generator uses artificial intelligence and data-driven algorithms to automatically create optimised fantasy cricket teams. Our AI engine applies risk-weighted player sampling, intelligent captain rotation, role constraints, and exposure controls to generate 20 unique, ready-to-enter teams for any cricket match.</div>
  </div>
  <div class="faq-item">
    <div class="faq-q" onclick="toggleFaq(this)">Is AI Fantasy Team Generator free to use? <span class="arrow">▼</span></div>
    <div class="faq-a">Yes, completely. The first 3 AI-generated teams are always fully visible and free. The remaining teams unlock instantly by watching a short 5-second simulated ad — no payment, subscription, or account creation required.</div>
  </div>
  <div class="faq-item">
    <div class="faq-q" onclick="toggleFaq(this)">Which cricket tournaments does it support? <span class="arrow">▼</span></div>
    <div class="faq-a">AI Fantasy Team Generator works for all major cricket tournaments — IPL, ICC T20 World Cup, ICC ODI World Cup, ICC Champions Trophy, Big Bash League, The Hundred, SA20, ILT20, Caribbean Premier League, and all international T20 and ODI bilateral series.</div>
  </div>
  <div class="faq-item">
    <div class="faq-q" onclick="toggleFaq(this)">Can I export my AI-generated teams? <span class="arrow">▼</span></div>
    <div class="faq-a">Yes. After unlocking all teams, an "Export All as PDF" button appears. This downloads a clean, formatted PDF showing all 20 AI-generated teams — each with captain, vice-captain, all 11 players, roles, and risk levels.</div>
  </div>
  <div class="faq-item">
    <div class="faq-q" onclick="toggleFaq(this)">Are AI-generated fantasy cricket teams guaranteed to win? <span class="arrow">▼</span></div>
    <div class="faq-a">No. AI Fantasy Team Generator is an informational and entertainment tool. Performance in fantasy contests depends entirely on real match outcomes which no AI can predict with certainty. Always play responsibly.</div>
  </div>

</section>

""" + _FOOTER + _AD_MODAL + """

<script>
var selT1=null, selT2=null, selMID=null, selMode=null;

(function() {
  try {
    if (localStorage.getItem('fantasyxi_age_ok') === '1') {
      var gate = document.getElementById('ageGate');
      if (gate) gate.style.display = 'none';
    }
  } catch(e) {}
})();

function ageConfirm(isAdult) {
  var gate    = document.getElementById('ageGate');
  var blocked = document.getElementById('ageBlocked');
  if (isAdult) {
    try { localStorage.setItem('fantasyxi_age_ok', '1'); } catch(e) {}
    if (gate) {
      gate.style.transition = 'opacity .3s';
      gate.style.opacity = '0';
      setTimeout(function() { gate.style.display = 'none'; }, 300);
    }
  } else {
    if (gate)    gate.style.display    = 'none';
    if (blocked) blocked.style.display = 'flex';
  }
}

function setStep(n) {
  for (var i = 1; i <= 4; i++) {
    var el = document.getElementById('step' + i);
    if (!el) continue;
    el.classList.remove('done', 'active');
    if (i < n)  el.classList.add('done');
    if (i === n) el.classList.add('active');
  }
}
setStep(1);

function showTab(id, el) {
  document.getElementById('tab-up').style.display  = id === 'up'  ? '' : 'none';
  document.getElementById('tab-man').style.display = id === 'man' ? '' : 'none';
  document.querySelectorAll('.tab-btn').forEach(function(b) {
    b.classList.remove('active'); b.setAttribute('aria-selected', 'false');
  });
  el.classList.add('active'); el.setAttribute('aria-selected', 'true');
}

function toggleAdv(header) {
  var body  = document.getElementById('advBody');
  var arrow = header.querySelector('.adv-header-arrow');
  var isOpen = arrow.classList.contains('open');
  if (isOpen) {
    body.style.display = 'none'; arrow.classList.remove('open');
    header.setAttribute('aria-expanded', 'false');
  } else {
    body.style.display = ''; arrow.classList.add('open');
    header.setAttribute('aria-expanded', 'true');
  }
}

function selectMatch(id, t1, t2, date, venue, el) {
  selMID = id; selT1 = t1; selT2 = t2;
  document.querySelectorAll('.match-card').forEach(function(c) { c.classList.remove('selected'); });
  el.classList.add('selected');
  var info = document.getElementById('selInfo');
  info.style.display = 'block';
  info.innerHTML = '✅ <strong>' + t1 + ' vs ' + t2 + '</strong> · ' + date + ' · 📍 ' + venue;
  populatePlayerChips(t1, t2);
  setStep(2);
  setTimeout(function() { scrollToId('section-mode'); }, 260);
}

function setManual() {
  var t1 = document.getElementById('mt1').value;
  var t2 = document.getElementById('mt2').value;
  if (t1 === t2) { showToast('Please select two different teams!', '#ff4d6d'); return; }
  selT1 = t1; selT2 = t2; selMID = 'manual';
  populatePlayerChips(t1, t2);
  setStep(2);
  showToast('✅ Teams confirmed! Choose a mode.', '#f5c842');
  setTimeout(function() { scrollToId('section-mode'); }, 260);
}

function selectMode(m, el) {
  selMode = m;
  document.querySelectorAll('.mode-card').forEach(function(c) {
    c.classList.remove('active'); c.setAttribute('aria-checked', 'false');
  });
  el.classList.add('active'); el.setAttribute('aria-checked', 'true');
  setStep(3);
  setTimeout(function() { scrollToId('section-criteria'); }, 260);
}

var allPlayers = {{ players_json|tojson }};
var lockedIds = [], excludedIds = [];

function populatePlayerChips(t1, t2) {
  lockedIds = []; excludedIds = [];
  updateSummary('lock'); updateSummary('excl');
  var teams = [
    { name: t1, players: (allPlayers[t1] || []).slice(0, 11) },
    { name: t2, players: (allPlayers[t2] || []).slice(0, 11) }
  ];
  function buildPicker(cid, type) {
    var container = document.getElementById(cid);
    if (!container) return;
    container.innerHTML = '';
    teams.forEach(function(team) {
      var lbl = document.createElement('div'); lbl.className = 'chip-team-lbl'; lbl.textContent = team.name;
      container.appendChild(lbl);
      var row = document.createElement('div'); row.className = 'chip-row';
      (team.players || []).forEach(function(p) {
        var chip = document.createElement('button');
        chip.type = 'button'; chip.className = 'pchip';
        chip.dataset.id = p.id; chip.dataset.name = p.name; chip.dataset.type = type;
        var rs = p.role.replace('Wicketkeeper-Batsman','WK').replace('All-rounder','AR').replace('Batsman','BAT').replace('Bowler','BOWL');
        chip.innerHTML = '<span class="pchip-name">' + p.name + '</span><span class="pchip-role">' + rs + '</span>';
        chip.onclick = function() { toggleChip(chip, type); };
        row.appendChild(chip);
      });
      container.appendChild(row);
    });
  }
  buildPicker('lock_picker', 'lock');
  buildPicker('excl_picker', 'excl');
}

function toggleChip(chip, type) {
  var id = chip.dataset.id, name = chip.dataset.name;
  var arr   = (type === 'lock') ? lockedIds : excludedIds;
  var other = (type === 'lock') ? excludedIds : lockedIds;
  if (other.indexOf(id) !== -1) { showToast('⚠️ ' + name + ' is already in the other list.', '#ff4d6d'); return; }
  var idx = arr.indexOf(id);
  if (idx === -1) {
    arr.push(id);
    chip.classList.add(type === 'lock' ? 'pchip--active' : 'pchip--active-excl');
  } else {
    arr.splice(idx, 1);
    chip.classList.remove('pchip--active', 'pchip--active-excl');
  }
  updateSummary(type);
}

function updateSummary(type) {
  var arr = (type === 'lock') ? lockedIds : excludedIds;
  var el  = document.getElementById(type + '_summary');
  if (!el) return;
  if (!arr.length) { el.innerHTML = ''; return; }
  var cls = (type === 'lock') ? 'pchip--active' : 'pchip--active-excl';
  var names = [];
  document.querySelectorAll('.pchip.' + cls + '[data-type="' + type + '"]').forEach(function(c) { names.push(c.dataset.name); });
  var col = (type === 'lock') ? 'var(--grn)' : 'var(--red)';
  el.innerHTML = '<span style="color:' + col + ';font-weight:700;">' + (type === 'lock' ? '🔒' : '🚫') + ' ' + names.length + ' selected: </span>'
    + '<span style="color:var(--txt2);">' + names.join(', ') + '</span>';
}

function doGenerate() {
  if (!selT1 || !selT2) { showToast('Please select a match first!', '#ff4d6d'); return; }
  if (!selMode)          { showToast('Please choose a generation mode!', '#ff4d6d'); return; }

  var cr = {};
  ['c1','c6','c7','c8','c11','c12','c13','c14','c15'].forEach(function(k) {
    var el = document.getElementById(k); cr[k] = el ? el.checked : true;
  });

  var adv = {
    unique_cap:    !!(document.getElementById('unique_cap')||{}).checked,
    unique_vc:     !!(document.getElementById('unique_vc')||{}).checked,
    differential:  !!(document.getElementById('differential')||{}).checked,
    balanced_dist: !!(document.getElementById('balanced_dist')||{}).checked,
    exposure_pct:  parseInt(document.getElementById('exposure').value) || 75,
    max_from_one:  parseInt(document.getElementById('max_from_one').value) || 7,
    risk_intensity:(parseFloat(document.getElementById('risk_intensity').value) || 10) / 10,
    rand_strength: (parseFloat(document.getElementById('rand_strength').value) || 5) / 10,
    min_diff:      parseInt(document.getElementById('min_diff').value) || 0,
    safe_core:     false,
    locked:        lockedIds.slice(),
    excluded:      excludedIds.slice()
  };

  var nt = Math.min(parseInt(document.getElementById('nt').value) || 20, 20);
  var payload = { team1: selT1, team2: selT2, match_id: selMID, mode: selMode, nt: nt, cr: cr, adv: adv };

  setStep(4);
  var spin = document.getElementById('spinnerOverlay');
  var btn  = document.getElementById('generateBtn');
  if (spin) spin.classList.add('active');
  if (btn)  { btn.disabled = true; btn.style.opacity = '.65'; btn.textContent = 'Generating…'; }

  var form = document.createElement('form');
  form.method = 'POST'; form.action = '/generate';
  var inp = document.createElement('input');
  inp.type = 'hidden'; inp.name = 'payload'; inp.value = JSON.stringify(payload);
  form.appendChild(inp); document.body.appendChild(form);
  setTimeout(function() { form.submit(); }, 150);
}

function resetAll() {
  selT1 = selT2 = selMID = selMode = null; lockedIds = []; excludedIds = [];
  document.querySelectorAll('.match-card').forEach(function(c) { c.classList.remove('selected'); });
  document.querySelectorAll('.mode-card').forEach(function(c) { c.classList.remove('active'); c.setAttribute('aria-checked','false'); });
  var info = document.getElementById('selInfo');
  if (info) info.style.display = 'none';
  ['lock_picker','excl_picker'].forEach(function(id) {
    var el = document.getElementById(id);
    if (el) el.innerHTML = '<span class="chip-placeholder">Select a match first</span>';
  });
  ['lock_summary','excl_summary'].forEach(function(id) {
    var el = document.getElementById(id); if (el) el.innerHTML = '';
  });
  setStep(1);
  showToast('🔄 Reset complete. Select a match to start.', '#4db8ff');
  scrollToId('tool');
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
<script async src="https://www.googletagmanager.com/gtag/js?id=G-VJS4H89EKW"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){dataLayer.push(arguments);}
  gtag('js', new Date());
  gtag('config', 'G-VJS4H89EKW');
</script>
<title>AI Fantasy Team Generator — {{team1}} vs {{team2}} · {{teams|length}} Teams Generated</title>
<meta name="description" content="{{teams|length}} AI-generated fantasy cricket teams for {{team1}} vs {{team2}}. {{mode|capitalize}} mode. AI Fantasy Team Generator.">
<meta name="robots" content="noindex, nofollow">
""" + _CSS + """
</head>
<body>

<header role="banner">
  <div class="logo-wrap">
    <a href="/" class="logo">⚡ AI Fantasy Team Generator</a>
  </div>
  <nav class="hdr-nav" aria-label="Results navigation">
    <a href="/">← New Generation</a>
    <a href="/export_pdf" id="pdfBtn" class="cta" {% if not unlocked %}style="display:none"{% endif %}>📄 Export PDF</a>
  </nav>
</header>

<div class="step-bar" aria-label="Progress steps">
  <div class="step-bar-inner">
    <div class="step done"><div class="step-num">1</div><span class="step-lbl">Select Match</span><div class="step-line"></div></div>
    <div class="step done"><div class="step-num">2</div><span class="step-lbl">Choose Mode</span><div class="step-line"></div></div>
    <div class="step done"><div class="step-num">3</div><span class="step-lbl">Set Criteria</span><div class="step-line"></div></div>
    <div class="step active"><div class="step-num">4</div><span class="step-lbl">Generated ✓</span></div>
  </div>
</div>

<div class="success-banner z1" role="status">
  <span>✅</span>
  <div>
    <strong>{{teams|length}} AI Teams Generated Successfully!</strong>
    <span class="success-sub">First 3 are instantly free · Watch a 5-second ad to unlock all {{teams|length - 3}} remaining AI teams</span>
  </div>
</div>

<main class="wrap z1">

  <div class="match-strip">
    <div>
      <div class="strip-vs">{{team1}}<em>VS</em>{{team2}}</div>
      {% if venue %}<div class="strip-venue">📍 {{venue}}</div>{% endif %}
    </div>
    <div class="strip-right">
      <span class="pill pill-{{mode}}">{{mode|upper}}</span>
      <span class="pill pill-neutral">{{teams|length}} Teams</span>
      <span class="pill pill-neutral">XI Only</span>
    </div>
  </div>

  <div class="stats-bar">
    <div class="stat-chip"><strong>{{teams|length}}</strong><span>Total Teams</span></div>
    <div class="stat-chip"><strong>3</strong><span>Free Preview</span></div>
    <div class="stat-chip"><strong>{{teams|length - 3}}</strong><span>Locked</span></div>
    <div class="stat-chip"><strong>{{unique_caps}}</strong><span>Captains Used</span></div>
    <div class="stat-chip"><strong>{{cv_combos}}</strong><span>C/VC Combos</span></div>
    <div class="stat-chip"><strong>XI Only</strong><span>Player Pool</span></div>
  </div>

  <div class="res-topbar">
    <div class="sh" style="margin-bottom:0;">Your Generated Teams</div>
    {% if unlocked %}
    <a href="/export_pdf" class="btn btn-grn" style="font-size:.85rem;padding:9px 18px;">📄 Export All as PDF</a>
    {% endif %}
  </div>

  <div class="team-grid" id="mainGrid">

    {% for t in teams[:3] %}
    <div class="team-card fade-up" style="animation-delay:{{loop.index0 * 0.05}}s;">
      <div class="team-hdr">
        <div class="team-num">Team {{loop.index}}</div>
        <span class="badge badge-free">FREE ✓</span>
      </div>
      <div class="cv-row">
        <div class="cv-pill cv-c"><span class="cv-lbl">Captain 2×</span><span class="cv-nm">{{t.captain}}</span></div>
        <div class="cv-pill cv-vc"><span class="cv-lbl">Vice Captain 1.5×</span><span class="cv-nm">{{t.vice_captain}}</span></div>
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

    {% if not unlocked %}
    <div class="unlock-banner fade-up" id="unlockBanner" style="animation-delay:.16s;">
      <div class="unlock-count">🤖 {{teams|length - 3}} AI Teams Waiting</div>
      <h3>Unlock All {{teams|length - 3}} Remaining AI Teams</h3>
      <div class="unlock-perks">
        <span class="unlock-perk">✅ Completely free</span>
        <span class="unlock-perk">⏱ Takes 5 seconds</span>
        <span class="unlock-perk">📋 Copy any team</span>
        <span class="unlock-perk">📄 Export to PDF</span>
      </div>
      <p>Watch one short simulated 5-second ad — then all teams unlock instantly.</p>
      <button class="btn btn-ora btn-xl" onclick="openAd()" id="watchAdBtn">
        ▶ Watch 1 Ad → Unlock All Teams
      </button>
    </div>
    {% endif %}

    {% for t in teams[3:] %}
    <div class="team-card fade-up" style="animation-delay:{{(loop.index + 2) * 0.03}}s;">
      <div class="team-hdr">
        <div class="team-num">Team {{loop.index + 3}}</div>
        <span class="badge badge-lock">🔒 LOCKED</span>
      </div>
      <div class="cv-row">
        <div class="cv-pill cv-c"><span class="cv-lbl">Captain 2×</span><span class="cv-nm">{{t.captain}}</span></div>
        <div class="cv-pill cv-vc"><span class="cv-lbl">Vice Captain 1.5×</span><span class="cv-nm">{{t.vice_captain}}</span></div>
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
        <button class="copy-btn" disabled>📋 Copy</button>
        {% else %}
        <button class="copy-btn" onclick="copyTeam({{loop.index + 2}})">📋 Copy</button>
        {% endif %}
      </div>
      {% if not unlocked %}
      <div class="lock-ov">
        <div class="lock-ico">🔒</div>
        <div class="lock-lbl">LOCKED</div>
        <div class="lock-sub">Watch ad to unlock instantly</div>
      </div>
      {% endif %}
    </div>
    {% endfor %}

  </div>

  {% if unlocked %}
  <div style="text-align:center;margin:36px 0;">
    <a href="/export_pdf" class="btn btn-grn btn-xl">📄 Export All {{teams|length}} Teams as PDF</a>
  </div>
  {% endif %}

  <div style="text-align:center;margin-top:22px;">
    <a href="/" class="btn btn-ghost">← Generate New Teams</a>
  </div>

</main>

""" + _FOOTER + _AD_MODAL + _SHARED_JS + """
</body>
</html>
"""

# =============================================================================
# ─── LEGAL PAGES ─────────────────────────────────────────────────────────────
# =============================================================================

def legal_wrap(title, body):
    return """<!DOCTYPE html>
<html lang="en">
<head>
<script async src="https://www.googletagmanager.com/gtag/js?id=G-VJS4H89EKW"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){dataLayer.push(arguments);}
  gtag('js', new Date());
  gtag('config', 'G-VJS4H89EKW');
</script>
<title>""" + title + """ — AI Fantasy Team Generator</title>
<meta name="robots" content="index, follow">
""" + _CSS + """
</head>
<body>
<header>
  <div class="logo-wrap">
    <a href="/" class="logo">⚡ AI Fantasy Team Generator</a>
  </div>
  <nav class="hdr-nav">
    <a href="/">← Home</a>
    <a href="/about">About</a>
    <a href="/contact">Contact</a>
  </nav>
</header>
<div class="legal-wrap z1">""" + body + """</div>
""" + _FOOTER + """
<div class="toast" id="toast" role="status" aria-live="polite"></div>
<script>
function showToast(msg,col){ var t=document.getElementById('toast'); if(!t)return; t.textContent=msg; t.style.background=col||'#00e5a0'; t.style.color='#000'; t.classList.add('show'); setTimeout(function(){t.classList.remove('show');},3000); }
</script>
</body>
</html>"""

PRIVACY_BODY = """
<h1>Privacy Policy</h1>
<p class="last-updated">Last updated: February 2026</p>
<h2>Introduction</h2>
<p>AI Fantasy Team Generator ("we", "our", "us") is committed to protecting your personal information and your right to privacy. This Privacy Policy explains how we collect, use, disclose, and safeguard your information when you visit our website at fantasyxi.in.</p>
<h2>Information We Collect</h2>
<p>We may collect the following categories of information:</p>
<ul>
  <li><strong>Log and Usage Data:</strong> Server logs, IP addresses, browser type, pages visited, referring URL, and time of visit.</li>
  <li><strong>Cookies and Tracking Technologies:</strong> We and our advertising partners use cookies and similar tracking technologies.</li>
  <li><strong>Contact Form Data:</strong> If you contact us, we collect your name, email address, subject, and message content.</li>
  <li><strong>Session Data:</strong> Temporary session data is stored server-side to maintain your generated teams within a browsing session.</li>
</ul>
<h2>Google AdSense and Third-Party Advertising</h2>
<p>AI Fantasy Team Generator uses Google AdSense to display advertisements. Google AdSense uses cookies to serve ads based on your prior visits to this website or other websites. You may opt out of personalised advertising by visiting <a href="https://www.google.com/settings/ads" target="_blank" rel="noopener">Google Ad Settings</a>.</p>
<h2>Children's Privacy</h2>
<p>This website is intended for users aged 18 and over. We do not knowingly collect personally identifiable information from anyone under the age of 18.</p>
<h2>Contact Us</h2>
<p>If you have questions about this Privacy Policy, contact us at: <a href="/contact">our contact form</a> or via our <a href="/contact">Contact page</a>.</p>
"""

TERMS_BODY = """
<h1>Terms &amp; Conditions</h1>
<p class="last-updated">Last updated: February 2026</p>
<h2>Acceptance of Terms</h2>
<p>By accessing and using AI Fantasy Team Generator ("the website", "the service"), you accept and agree to be bound by these Terms and Conditions.</p>
<h2>Age Restriction</h2>
<p>This website is intended for users who are 18 years of age or older. By using this site, you represent and warrant that you are at least 18 years old.</p>
<h2>No Guarantee of Winnings</h2>
<p>AI Fantasy Team Generator is a team suggestion and educational tool only. We make no guarantee regarding any financial outcomes arising from the use of our generated teams in fantasy sports contests.</p>
<h2>Intellectual Property</h2>
<p>AI Fantasy Team Generator is not affiliated with, authorised by, or associated with Dream11, MyTeam11, ICC, BCCI, or any other official body.</p>
<h2>Governing Law</h2>
<p>These Terms shall be governed and construed in accordance with the laws of India.</p>
<h2>Contact</h2>
<p>For any questions regarding these Terms, please contact us at <a href="/contact">our contact form</a>.</p>
"""

ABOUT_BODY = """
<h1>About AI Fantasy Team Generator</h1>
<p class="last-updated">India's #1 AI Fantasy Team Generator for cricket — IPL, T20 World Cup, ICC tournaments and all major leagues</p>

<div class="about-grid">
  <div class="about-card"><div class="about-icon">🤖</div><h3>AI-Powered Engine</h3><p>Multi-layer AI distribution algorithm generates 20 unique, optimised teams with zero duplicates and valid role constraints — every single time.</p></div>
  <div class="about-card"><div class="about-icon">🏆</div><h3>All Tournaments</h3><p>Full support for IPL, T20 World Cup, ICC ODI World Cup, Big Bash, The Hundred, SA20, CPL and all international cricket series.</p></div>
  <div class="about-card"><div class="about-icon">📊</div><h3>Data-Driven</h3><p>AI risk-weighted player sampling, C/VC rotation intelligence, exposure limits, lock/exclude controls — all fully automated.</p></div>
  <div class="about-card"><div class="about-icon">🔒</div><h3>Privacy First</h3><p>No login required. No personal data permanently stored. Session data only. Fully AdSense compliant and transparent.</p></div>
  <div class="about-card"><div class="about-icon">📱</div><h3>Mobile Ready</h3><p>Fully responsive AI team generator optimised for mobile, tablet, and desktop.</p></div>
  <div class="about-card"><div class="about-icon">🆓</div><h3>Always Free</h3><p>The first 3 AI-generated teams are always free. Full access unlocks by watching a 5-second ad. No payment ever required.</p></div>
</div>

<h2>Our Mission</h2>
<p>AI Fantasy Team Generator was built to give fantasy cricket players of all skill levels access to a professional-grade AI fantasy team generator. Instead of spending hours manually creating teams, our AI engine applies proven distribution algorithms — automatically generating 20 optimised, diverse Dream11 teams for any cricket match in seconds.</p>

<h2>Disclaimer</h2>
<p>AI Fantasy Team Generator is an independent AI informational tool. It is not affiliated with Dream11, MyTeam11, ICC, BCCI, or any official cricket or fantasy sports organisation. Fantasy sports involve financial risk — please play responsibly. This tool is for users aged 18 and above.</p>
<p>Questions or feedback? Visit our <a href="/contact">Contact page</a>.</p>
"""

HOW_BODY = """
<h1>How AI Fantasy Team Generator Works</h1>
<p class="last-updated">A complete step-by-step guide to generating AI-powered fantasy cricket teams</p>

<h2>Step 1 — Select a Match</h2>
<p>From the home page, choose any upcoming cricket match from the match cards. Clicking a card confirms your selection and automatically scrolls you to the AI Mode selection. You can also use the Manual Selection tab to choose any two teams for any match not listed.</p>

<h2>Step 2 — Choose an AI Generation Mode</h2>
<p><strong>Safe mode</strong> weights low-risk players heavily — ideal for small contests. <strong>Balanced mode</strong> mixes low and medium risk, ideal for mid-size contests. <strong>Risky mode</strong> focuses on high-risk differentials, best for IPL grand leagues and mega contests.</p>

<h2>Step 3 — Configure AI Criteria (Optional)</h2>
<p>Fine-tune the AI with advanced options: set team count (up to 20), control player exposure limits, lock specific players, exclude specific players, enable differential injection, and more.</p>

<h2>Step 4 — Generate AI Teams and Review</h2>
<p>Click "Generate AI Teams." The AI produces unique fantasy lineups in seconds. The first 3 teams are immediately free. Watch a 5-second simulated ad to unlock all remaining teams instantly.</p>

<h2>Step 5 — Copy or Export</h2>
<p>Each team card has a one-click Copy button. After unlocking, export all teams as a clean formatted PDF for offline reference.</p>
"""

DISCLAIMER_BODY = """
<h1>Disclaimer</h1>
<p class="last-updated">Last updated: February 2026</p>
<h2>General Disclaimer</h2>
<p>All information provided by AI Fantasy Team Generator on this website is for general informational and entertainment purposes only.</p>
<h2>Fantasy Sports Disclaimer</h2>
<p>Fantasy sports involve an element of financial risk and may be habit-forming. Please play responsibly and within your means. AI Fantasy Team Generator does not guarantee any winnings.</p>
<h2>Affiliation Disclaimer</h2>
<p>AI Fantasy Team Generator is an entirely independent website and is not affiliated with, authorised by, maintained, sponsored, or endorsed by Dream11, MyTeam11, ICC, BCCI, or any other fantasy sports platform or cricket governing body.</p>
<h2>18+ Notice</h2>
<p>This website is strictly intended for users aged 18 and above.</p>
<h2>Contact</h2>
<p>Questions about this Disclaimer? Contact us at <a href="/contact">our contact form</a>.</p>
"""

CONTACT_BODY = """
<h1>Contact Us</h1>
<p class="last-updated">We'd love to hear from you — feedback, bug reports, or partnership enquiries.</p>

<h2>Get in Touch</h2>
<p>📧 Use the form below — we respond within 48 business hours.</p>
<p>We aim to respond to all enquiries within 48 business hours.</p>

<h2>Send a Message</h2>
<form class="contact-form" id="contactForm" onsubmit="submitForm(event)" novalidate>
  <div class="form-group">
    <label for="cf-name">Your Name *</label>
    <input type="text" id="cf-name" placeholder="Rahul Sharma" required autocomplete="name">
  </div>
  <div class="form-group">
    <label for="cf-email">Email Address *</label>
    <input type="email" id="cf-email" placeholder="rahul@example.com" required autocomplete="email">
  </div>
  <div class="form-group">
    <label for="cf-subject">Subject</label>
    <select id="cf-subject">
      <option>General Enquiry</option>
      <option>Bug Report</option>
      <option>Feature Request</option>
      <option>Data / Squad Update</option>
      <option>Partnership / Advertising</option>
      <option>Other</option>
    </select>
  </div>
  <div class="form-group">
    <label for="cf-msg">Message *</label>
    <textarea id="cf-msg" placeholder="Your message here..." required></textarea>
  </div>
  <button type="submit" class="btn btn-gold btn-lg" id="submitBtn">Send Message →</button>
</form>

<div class="form-msg" id="formMsg" style="display:none;">
  ✅ Thank you! Your message has been received. We'll get back to you within 48 business hours.
</div>

<div id="formError" style="display:none;background:rgba(255,77,109,.08);border:1px solid rgba(255,77,109,.25);border-radius:8px;padding:13px 16px;font-size:.82rem;color:#ff4d6d;margin-top:12px;"></div>

<script>
function submitForm(e) {
  e.preventDefault();

  var name    = document.getElementById('cf-name').value.trim();
  var email   = document.getElementById('cf-email').value.trim();
  var subject = document.getElementById('cf-subject').value;
  var msg     = document.getElementById('cf-msg').value.trim();
  var errBox  = document.getElementById('formError');
  var btn     = document.getElementById('submitBtn');

  errBox.style.display = 'none';

  if (!name || !email || !msg) {
    showToast('Please fill in all required fields.', '#ff4d6d'); return;
  }
  if (!email.includes('@')) {
    showToast('Please enter a valid email address.', '#ff4d6d'); return;
  }

  // Show loading state
  btn.disabled = true;
  btn.textContent = '⏳ Sending…';

  // 12-second client-side timeout — button never stays stuck
  var timedOut = false;
  var timer = setTimeout(function() {
    timedOut = true;
    // Server likely received it but response was slow — show success anyway
    document.getElementById('contactForm').style.display = 'none';
    document.getElementById('formMsg').style.display     = 'block';
    showToast('✅ Message sent!', '#00e5a0');
  }, 12000);

  fetch('/send_contact', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name: name, email: email, subject: subject, message: msg })
  })
  .then(function(r) { return r.json(); })
  .then(function(d) {
    clearTimeout(timer);
    if (timedOut) return; // already showed success via timeout
    if (d.success) {
      document.getElementById('contactForm').style.display = 'none';
      document.getElementById('formMsg').style.display     = 'block';
      showToast('✅ Message sent successfully!', '#00e5a0');
    } else {
      errBox.textContent    = '❌ ' + (d.error || 'Something went wrong. Please try again.');
      errBox.style.display  = 'block';
      btn.disabled          = false;
      btn.textContent       = 'Send Message →';
    }
  })
  .catch(function() {
    clearTimeout(timer);
    if (timedOut) return;
    errBox.textContent   = '❌ Network error. Please check your connection and try again.';
    errBox.style.display = 'block';
    btn.disabled         = false;
    btn.textContent      = 'Send Message →';
  });
}
</script>
"""

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
        tournament=td.get("tournament", "AI Fantasy Team Generator"),
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

    session["gen"] = {
        "teams": teams, "team1": team1, "team2": team2,
        "mode": mode, "venue": venue
    }
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
    """Zero external libraries — renders a print-ready HTML page.
    The browser's built-in Save as PDF does the conversion.
    No reportlab, no weasyprint, no wkhtmltopdf needed."""
    gen      = session.get("gen", {})
    teams    = gen.get("teams", [])
    if not teams:
        return "No teams found. Please generate teams first.", 400

    team1    = gen.get("team1", "T1")
    team2    = gen.get("team2", "T2")
    mode     = gen.get("mode", "balanced").upper()
    venue    = gen.get("venue", "")
    unlocked = session.get("unlocked", False)
    max_idx  = len(teams) if unlocked else 3

    role_abbr = {
        "Wicketkeeper-Batsman": "WK",
        "Batsman": "BAT",
        "All-rounder": "AR",
        "Bowler": "BOWL",
    }
    risk_color = {"Low": "#00e5a0", "Medium": "#4db8ff", "High": "#ff4d6d"}

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
              </td>
            </tr>"""

        cards_html += f"""
        <div class="team-card">
          <div class="card-hdr">
            <span class="team-num">Team {idx+1}</span>
            <span class="badge">{"FREE ✓" if idx < 3 else "UNLOCKED"}</span>
          </div>
          <div class="cv-strip">
            <div class="cv-box">
              <div class="cv-lbl">Captain 2×</div>
              <div class="cv-name cap">{t["captain"]}</div>
            </div>
            <div class="cv-box">
              <div class="cv-lbl">Vice Captain 1.5×</div>
              <div class="cv-name vc">{t["vice_captain"]}</div>
            </div>
          </div>
          <table class="player-table" width="100%" cellspacing="0">
            <thead>
              <tr style="background:#f8f8f8;">
                <th style="padding:5px 8px;text-align:left;font-size:.72rem;color:#888;font-weight:600;">PLAYER</th>
                <th style="padding:5px 8px;text-align:left;font-size:.72rem;color:#888;font-weight:600;">ROLE</th>
                <th style="padding:5px 8px;text-align:center;font-size:.72rem;color:#888;font-weight:600;">RISK</th>
              </tr>
            </thead>
            <tbody>{players_rows}</tbody>
          </table>
          <div class="card-foot">{t["from_t1"]} from {team1} &nbsp;·&nbsp; {t["from_t2"]} from {team2}</div>
        </div>"""

    venue_line = f"<p style='margin:2px 0 0;font-size:.8rem;color:#666;'>📍 {venue}</p>" if venue else ""

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>AI Fantasy Teams — {team1} vs {team2}</title>
<style>
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  body {{ font-family: Arial, Helvetica, sans-serif; background:#fff; color:#111; font-size:13px; }}

  .site-header {{
    background: linear-gradient(135deg,#f5c842,#d4a212);
    padding: 14px 24px; display:flex; justify-content:space-between; align-items:center;
  }}
  .site-header h1 {{ font-size:1.1rem; font-weight:800; color:#000; letter-spacing:1px; }}
  .site-header p  {{ font-size:.72rem; color:#222; }}

  .meta-bar {{
    background:#111; color:#fff; padding:10px 24px;
    display:flex; align-items:center; gap:16px; flex-wrap:wrap;
  }}
  .meta-bar .vs  {{ font-size:1.1rem; font-weight:800; letter-spacing:1px; }}
  .meta-bar .vs em {{ color:#f5c842; font-style:normal; margin:0 6px; font-size:.8rem; }}
  .pill {{
    display:inline-block; padding:2px 10px; border-radius:100px;
    font-size:.65rem; font-weight:700; letter-spacing:.8px; border:1px solid;
  }}
  .pill-safe    {{ background:rgba(0,229,160,.15);  color:#00e5a0; border-color:rgba(0,229,160,.3); }}
  .pill-balanced{{ background:rgba(77,184,255,.15); color:#4db8ff; border-color:rgba(77,184,255,.3); }}
  .pill-risky   {{ background:rgba(255,77,109,.15); color:#ff4d6d; border-color:rgba(255,77,109,.3); }}
  .pill-neutral {{ background:rgba(255,255,255,.1); color:#ccc;    border-color:rgba(255,255,255,.2); }}

  .print-note {{
    background:#fffbea; border:1px solid #f5c842; border-radius:8px;
    padding:12px 20px; margin:18px 20px; font-size:.82rem; color:#7a5c00;
    display:flex; align-items:center; gap:10px;
  }}
  .print-note button {{
    background:linear-gradient(135deg,#f5c842,#d4a212); border:none; border-radius:6px;
    padding:7px 18px; font-size:.82rem; font-weight:700; cursor:pointer; color:#000;
    white-space:nowrap;
  }}
  .print-note button:hover {{ opacity:.9; }}

  .teams-wrap {{
    display:grid;
    grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
    gap:14px; padding:0 20px 30px;
  }}

  .team-card {{
    border:1px solid #ddd; border-radius:10px; overflow:hidden;
    break-inside:avoid; page-break-inside:avoid;
  }}
  .card-hdr {{
    background:linear-gradient(135deg,#1a1e30,#0d1020);
    padding:9px 13px; display:flex; justify-content:space-between; align-items:center;
  }}
  .team-num {{ color:#f5c842; font-weight:800; font-size:.88rem; letter-spacing:2px; }}
  .badge    {{ background:#00e5a0; color:#000; font-size:.6rem; font-weight:800;
               padding:2px 9px; border-radius:100px; letter-spacing:.8px; }}

  .cv-strip {{ display:flex; gap:6px; padding:9px 10px 6px; background:#fafafa; }}
  .cv-box   {{ flex:1; border:1px solid #eee; border-radius:6px; padding:6px 8px; text-align:center; }}
  .cv-lbl   {{ font-size:.58rem; color:#999; text-transform:uppercase; letter-spacing:.4px; margin-bottom:2px; font-weight:600; }}
  .cv-name  {{ font-weight:700; font-size:.78rem; }}
  .cv-name.cap {{ color:#b8860b; }}
  .cv-name.vc  {{ color:#1a6fa6; }}

  .player-table {{ border-collapse:collapse; }}
  .card-foot {{
    padding:7px 10px; background:#f8f8f8; border-top:1px solid #eee;
    font-size:.65rem; color:#888; text-align:center;
  }}

  @media print {{
    body {{ -webkit-print-color-adjust:exact; print-color-adjust:exact; }}
    .print-note {{ display:none !important; }}
    .site-header, .meta-bar {{ -webkit-print-color-adjust:exact; print-color-adjust:exact; }}
    .teams-wrap {{ grid-template-columns: repeat(2, 1fr); gap:10px; padding:0 10px 20px; }}
    @page {{ margin:12mm 10mm; size:A4; }}
  }}

  @media(max-width:600px) {{
    .teams-wrap {{ grid-template-columns:1fr; padding:0 12px 24px; }}
    .print-note {{ margin:12px; flex-direction:column; align-items:flex-start; gap:8px; }}
  }}
</style>
</head>
<body>

<div class="site-header">
  <div>
    <h1>⚡ AI Fantasy Team Generator</h1>
    <p>fantasyxi.in · AI-powered fantasy cricket teams</p>
  </div>
  <div style="text-align:right;">
    <div style="font-size:.75rem;color:#222;">{len(teams[:max_idx])} Teams · {mode} Mode</div>
    <div style="font-size:.65rem;color:#444;margin-top:2px;">{datetime.date.today().strftime("%d %b %Y")}</div>
  </div>
</div>

<div class="meta-bar">
  <span class="vs">{team1}<em>VS</em>{team2}</span>
  {venue_line.replace("style='", 'style="color:#bbb;font-size:.75rem;margin:0;"').replace("'", '"') if venue else ""}
  <span class="pill pill-{mode.lower()}">{mode}</span>
  <span class="pill pill-neutral">{len(teams[:max_idx])} Teams</span>
</div>

<div class="print-note">
  <span>💡 <strong>Save as PDF:</strong> Click the button → your browser will open Print → choose "Save as PDF"</span>
  <button onclick="window.print()">🖨 Save as PDF</button>
</div>

<div class="teams-wrap">
  {cards_html}
</div>

<script>
  // Auto-trigger print dialog after 600ms for instant PDF experience
  setTimeout(function() {{
    // Only auto-open if user came here directly (not navigating away)
    if (document.visibilityState === 'visible') {{
      window.print();
    }}
  }}, 800);
</script>
</body>
</html>"""

    return Response(html, mimetype="text/html")


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


@app.route("/send_contact", methods=["POST"])
def send_contact():
    """Validates input then fires email in background — responds instantly."""
    data    = request.get_json(silent=True) or {}
    name    = data.get("name", "").strip()
    email   = data.get("email", "").strip()
    subject = data.get("subject", "General Enquiry").strip()
    message = data.get("message", "").strip()

    if not name or not email or not message:
        return jsonify({"success": False, "error": "Please fill in all required fields."}), 400
    if "@" not in email or "." not in email.split("@")[-1]:
        return jsonify({"success": False, "error": "Please enter a valid email address."}), 400

    # Fire-and-forget: sends email in background, HTTP response returns immediately
    t = threading.Thread(target=_smtp_send, args=(name, email, subject, message), daemon=True)
    t.start()

    return jsonify({"success": True})


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


if __name__ == "__main__":
    app.run(debug=True, port=5000)
