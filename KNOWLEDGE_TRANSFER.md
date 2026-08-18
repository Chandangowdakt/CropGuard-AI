# CropGuard AI — Knowledge transfer

Tribal knowledge from git history (`109246d` → `8ddd6f8` on `main`) and the current codebase. Read this before changing models, `app.js`, or Render.

Related docs: `README.md` (setup), `ARCHITECTURE.md` (design).

---

## 1. Bugs that already bit us (and how they were fixed)

### Class-index mismatch (Healthy shown as disease)

**What happened.** `ImageFolder` assigns class indices in **alphabetical folder order**. An earlier 4-class trainer used a **hardcoded** class list that did not match that order. Softmax index `0` was labeled Healthy in code but Diseased on disk (and the reverse). The UI looked “confidently wrong.”

**Fix.** Checkpoints now store `class_to_idx`. Inference builds:

```text
class_names = [name for name, i in sorted(class_to_idx.items(), key=lambda x: x[1])]
label = class_names[argmax]
```

Training helper: `chrysanthemum_leaf_model/class_mapping.py` — evaluation **aborts** if checkpoint mapping ≠ folders.

**Do not** hardcode `["Healthy", "Bacterial", "Septoria"]` as logit order. Alphabetically it is `Bacterial`, `Healthy`, `Septoria`.

**Commit:** `3563fd2` (platform 3-class cutover). Mapping discipline lives in `ai_engine.py` / `leaf_engine.py`.

---

### GitHub Pages blank screen (Babel + ES modules)

**What happened.** Pages served `app.js` as an ES module (or used Babel `data-presets` / `type="text/babel"` incorrectly). Standalone Babel + `import`/`export` at line start produced a **white page** and a console module error.

**Fix.**

- `index.html` **fetches** `app.js`, `Babel.transform` with `{ presets: [["react", { runtime: "classic" }]] }`, injects a classic `<script>`.
- **Zero** `import`/`export` at the start of a line in `app.js`.

**Commits:** `2041761`, `e515cdd`, `ecb99c1`.

**Still true:** if you add `import React from "react"` to `app.js`, production Pages will go blank again.

---

### Render: no model / no torch / empty database

| Symptom | Cause | Fix | Commits |
|---------|--------|-----|---------|
| Login fails on fresh Render | SQLite on `/tmp` is empty after restart | Auto-seed if no users (`ensure_seeded_if_empty`) | `85bff89`, `068ad10` |
| All predictions `unavailable` | `.pth` gitignored; native Python 3.14 has no torch wheel | Track leaf `.pth`; Docker **Python 3.11**; `build.sh` CPU torch | `a1b8f6b`, `1e93f74`, `cbff609`, `3867d67`, `31d5c66` |
| `email-validator` / Pydantic errors | missing extra | `pydantic[email]` + `email-validator` | `5f9a15b` |

**Still true:** `/tmp/cropguard.db` **vanishes** on Render restart. Demo users come back via seed; farmer-uploaded history does not. Do not treat Render SQLite as production data.

---

### Weather widget 429 / red error

Open-Meteo rate-limited the dashboard.

**Fix:** 60-minute in-memory cache + fallback numbers + a muted UI note (not a hard error). Commit `b6837e6`.

---

### Live Scan: frames never analyzed after Start

`analyzeFrame` required `phase === "scanning"` but Start called `setInterval(analyzeFrame)` from the **previous render** (`phase` still `idle`). The interval kept the stale closure.

**Fix:** drive the camera loop with `useEffect([phase])` and `phaseRef`. Commit `e9ef281`.

---

### Live Scan: GPS dropped; no ScanSession

The UI used legacy `POST /api/scan/submit-session`, which did not persist GPS or create a durable session.

**Fix:** create → analyze-frame → bulk detections → complete. Keep `submit-session` for compatibility; Live Scan must not call it. Commit `ebfedf6`.

---

### Live Scan: farmer 403 mid-walk

`analyze-frame` required manager/admin; farmers could create a session then every frame 403’d, leaving `active` sessions.

**Fix:** Live Scan roles include `farmer`. Commit `19f6894`.

---

### Live Scan: video racing the AI

Uploaded video played in real time; AI sampled ~every 2s and waited on Render. Overlay lagged; `Frames: 1`.

**Fix:** **seek-step** for uploads only (pause → analyze → seek ~1.5s). Camera walk still uses wall-clock interval. Commit `8ddd6f8`.

---

### Alerts / counts inflated

- UI treated raw `actual_class` as an issue without `data.is_problem`.
- Healthy frames were sampled in the client **and again** every 5th in bulk save → problem **rate** looked worse than reality (urgent WhatsApp uses that rate).

**Fix:** persist on confirmed `is_problem`; one detection per plant zone; do not double-sample healthy. `e9ef281`, `19f6894`.

---

### Batch analysis: one bad file killed the batch

**Fix:** per-file try/except, error list, optional failed-files CSV. `0bc14ff`, `c08d76d`.

---

### HEIC / iPhone photos (partial, not a full library fix)

Pillow in this repo **does not decode HEIC**. Backend `_read_image_upload` only allows `.jpg/.jpeg/.png`. Frontend `validateImageFile` only allows those MIME types.

**What actually works today**

- **Live Scan camera** draws to a canvas and uploads **JPEG** (`toBlob(..., "image/jpeg")`) — iPhone HEIC never hits the API on that path.
- **Analysis / Leaf Scan file picker** still **rejects** `.heic`. Farmers who AirDrop a Camera roll file will see “Only JPG, PNG, and JPEG.”

That is a product gap, not a completed HEIC pipeline. Adding `pillow-heif` + converting to JPEG on upload is the proper fix if iOS gallery upload matters.

---

## 2. Things a new developer should be careful about

1. **`app.js` is not a module.** No line-start `import`/`export`. No JSX `type="text/babel"` with `data-presets`. Test Pages-style boot: fetch + Babel classic.

2. **Never invent class order.** Always `class_to_idx` from the `.pth`. If you retrain, copy **that** checkpoint into `backend/models/` and confirm `/api/health` prints the same class list.

3. **Local API port is 8001**, not 8000. Frontend `API_BASE` on localhost is hardcoded to 8001. Changing the backend port without changing `app.js` looks like a “dead API.”

4. **JWT `sub` is the user’s email**, not the numeric user id. Changing login to put `user.id` in `sub` will make every existing token fail `_resolve_user_from_token`.

5. **Two engines, one weight file.** `ai_engine` (Analysis + Live Scan) applies a **75%** uncertain gate. `leaf_engine` (Leaf Scan) does not. Don’t “simplify” by deleting one without updating both UIs. There are three different confidence numbers on purpose: **75%** Analysis rewrite-to-uncertain, **70%** Live Scan majority confirmation, **80%** WhatsApp send. Do not “unify” them without talking to whoever is running the field pilot.

6. **Live Scan analyze-frame writes no rows.** Persistence is bulk-on-submit. Smoothing state is **RAM** (`scan_smoothing._sessions`). A second Uvicorn worker or a restart resets confirmation windows.

7. **Do not DROP columns.** `database.py` only `ALTER TABLE ... ADD`. Legacy `diseased_count` / `pest_count` stay. Frontend still maps `diseased` → Bacterial for old rows.

8. **Farm ACL.** Always `get_farm_for_user`. Skipping it leaks other farmers’ data.

9. **Don’t sample healthy twice** if you change bulk save.

10. **PyTorch is not in `requirements.txt`.** Local: install CPU torch yourself. Render: Docker `build.sh`. Adding torch to requirements on Python 3.14 **will** break native Render builds (that is why Docker exists). Commit `1e93f74` put torch in requirements; later Docker commits reversed that approach.

11. **Demo passwords are public** (`admin123`, etc.). Fine for a pilot; not fine if this becomes a real tenant platform. Change `JWT_SECRET` on Render.

12. **Gitignored:** `.env`, `*.db`, `backend/storage/`. The **leaf** `.pth` is an exception in `.gitignore` so Render can ship weights.

13. **Pages cache.** After pushing frontend, hard-refresh; Actions deploy `frontend/` to `gh-pages`.

---

## 3. Hacky workarounds (and why they stay)

| Workaround | Where | Why it exists |
|------------|--------|----------------|
| Fetch `app.js` then Babel-transform in the browser | `frontend/index.html` | Pages has no webpack. Classic runtime was the only way to get JSX without a blank page. |
| `sys.stdout.reconfigure(encoding="utf-8")` copied in almost every `.py` | Many files | Windows consoles otherwise crash on `🌿` / non-ASCII prints. |
| passlib **then** native `bcrypt` | `auth.py` | passlib looks for `bcrypt.__about__` which newer bcrypt removed; Python 3.14 logs a trapped error but login still works. |
| `torch.load(..., weights_only=False)` | engines | Checkpoints are dicts with metadata, not raw tensors. `weights_only=True` would fail load. |
| CORS `allow_origins=["*", ...]` | `main.py` | Pages + local ports + “just make the demo work.” Tighten before a security review. |
| Default `JWT_SECRET` in source | `auth.py` | Local `start.bat` works with zero config. Production **must** override. |
| SQLite under `/tmp` when `RENDER` is set | `database.py` | Render disk is ephemeral; `/tmp` is writable. Data loss is accepted for the free tier. |
| Auto-seed admin/farmer/manager | `seed.py` + `main.py` lifespan | Empty Render DB otherwise made the live site unusable. |
| Download `.pth` from GitHub raw if missing | `ai_engine.ensure_model_available` | First boot / volume without git-lfs. Requires file ≥ ~5 MB or it is treated as garbage. |
| Center-crop 70% instead of a leaf detector | `leaf_focus.py` | No YOLO weights. Forces “look at the middle” on walking video. Bad if the leaf is in a corner. |
| In-memory WhatsApp cooldown | `whatsapp_alerts.py` | No Redis. Resets on deploy; two workers can double-send. |
| `datetime.utcnow()` still used in models/routers | many | Predates timezone-aware APIs. Auth token issue uses `datetime.now(timezone.utc)`. Mixing naive UTC in SQLite is “good enough” until Postgres. |
| Legacy `/submit-session` | `scan.py` | Old clients. Live Scan must keep using sessions APIs. |
| Dual class names in the SPA (`diseased` → Bacterial) | `normalizeClassKey` | Charts/badges for pre-cutover detections. |
| Shadow v2 CSV | `storage/shadow_predictions.csv` | Compare a 4-class-ish v2 head without showing it. File is gitignored with storage. |
| Weather fallback dict | `weather.py` | Open-Meteo 429s must not paint the dashboard red. |
| Canvas JPEG for Live Scan | `app.js` `toBlob` | Avoids iOS HEIC on the **camera** path without extra native deps. |
| `except Exception` on crop decode | `leaf_focus.py` | Prefer original bytes over crashing a walk. |
| WhatsApp in a daemon thread after commit | `scan.py` | Twilio latency must not fail bulk save. Failures only print. |
| `pagehide` + `fetch(..., keepalive: true)` cancel | Live Scan | Best-effort session cancel when the tab dies; may not run on all mobile browsers. |

These are not “nice architecture.” They are how a student/pilot stack survived Windows, Pages, and Render free.

---

## 4. Suggested next steps

Ordered by payoff vs risk.

### Pilot / product

1. **HEIC on Analysis/Leaf Scan** — `pillow-heif`, convert to JPEG server-side; accept `.heic` in `_read_image_upload` and the file picker. Camera path is already JPEG.
2. **Postgres** (or any durable DB) if Render data must survive deploys.
3. **Set `JWT_SECRET`**, rotate demo passwords, restrict CORS to Pages + localhost.
4. **Durable WhatsApp/email queue** (DB row + retry) instead of in-memory cooldown + fire-and-forget thread.
5. Field-test **seek-step video** on long clips (memory, 300 MB cap, seek reliability on Safari).

### Correctness / ML

6. Keep **class_to_idx tests** in CI: load checkpoint, assert names == `["Bacterial", "Healthy", "Septoria"]` in index order.
7. Recalibrate **75% uncertain** vs Live Scan **70% + majority** — two thresholds confuse operators.
8. Optional **leaf detector** only if center-crop fails in real rows (needs labeled boxes).
9. **On-device TFLite** only if farms have no network; large project, not a weekend change.

### Engineering hygiene

10. **Vite or similar** so `app.js` can be a real module and Pages does not depend on unpkg Babel. Highest-risk refactor; do it as its own PR with a Pages smoke test.
11. Alembic (or accept SQLite-only forever). Stop copying `ALTER TABLE` blocks.
12. Replace `datetime.utcnow()` with timezone-aware UTC.
13. Single Uvicorn worker documented, or move `scan_smoothing` to Redis/DB.
14. Don’t log Twilio-adjacent secrets; keep `.env` out of git (already gitignored).

---

## 5. Commit timeline (orientation)

| Commit | Meaning |
|--------|---------|
| `109246d` | Initial CropGuard |
| `da1e704` … `5f9a15b` | Render + Pages |
| `2041761`–`ecb99c1` | Blank Pages / Babel |
| `85bff89` | Auto-seed |
| `a1b8f6b`–`31d5c66` | Model + Docker + torch on Render |
| `b6837e6` | Weather cache |
| `84ede48` / `3563fd2` | 3-class leaf model everywhere |
| `32aced0`–`c08d76d` | Batch analysis |
| `ebfedf6`–`8ddd6f8` | Live Scan GPS, zones, UX, video, seek-step |
| `cff96e0` | Dashboard stat cards as navigation |

---

## 6. One-line memory

**Wrong class labels almost always mean mapping, not “the CNN is stupid.” A blank site almost always means `app.js` grew an `import`. A dead production model almost always means torch/Python 3.14 or a missing `.pth`.**
