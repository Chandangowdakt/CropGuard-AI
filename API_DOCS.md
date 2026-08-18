# CropGuard AI — API reference

Generated from the FastAPI routers in `backend/` (`main.py`, `routers/users.py`, `routers/farms.py`, `routers/detections.py`, `routers/scan.py`, `routers/alerts.py`) and Pydantic models in `backend/schemas.py`.

Interactive OpenAPI: `http://localhost:8001/docs` (Swagger) and `http://localhost:8001/redoc`.

---

## Base URLs

| Environment | Base |
|-------------|------|
| Local | `http://localhost:8001` |
| Production | `https://cropguard-ai-backend.onrender.com` |

The SPA on GitHub Pages calls the production base. On `localhost` it calls port **8001**.

---

## Authentication

Most routes require:

```http
Authorization: Bearer <JWT>
```

- Login and register return `access_token` (HS256, **7-day** expiry).
- JWT `sub` is the user’s **email**, not numeric id. `role` is also in the payload but the server looks up the user by email.
- Default secret is `cropguard-dev-jwt-secret-change-in-production` unless `JWT_SECRET` is set.

**Roles:** `farmer` | `manager` | `admin`

**Farm ACL** (`get_farm_for_user`): farmer → own farms; manager → assigned farms; admin → all farms. Missing farm → `404 Farm not found`. No access → `403 Access denied`.

**Common HTTP errors**

| Status | Meaning |
|--------|---------|
| 400 | Validation, bad file type, inactive session, duplicate email |
| 401 | Missing/invalid/expired token, bad login |
| 403 | Wrong role or farm not in ACL |
| 404 | Farm, user, session, detection, or alert not found |
| 503 | Model/torch unavailable, weather fetch failed |

**Demo accounts** (seeded): `admin@cropguard.ai` / `admin123`, `farmer@cropguard.ai` / `farmer123`, `manager@cropguard.ai` / `manager123`

**Image uploads (Analysis / Leaf Scan):** `.jpg` / `.jpeg` / `.png` only, max **10 MB**. HEIC is rejected. Live Scan frames skip the extension check (canvas JPEG).

**Prediction `class` field:** JSON uses `"class"` (serialization alias), not `predicted_class`. Canonical values: `Bacterial`, `Healthy`, `Septoria`. Analysis may also return `uncertain` or `unavailable`. Confidence is **0–100**, not 0–1.

---

## Endpoint index

| Method | Path | Auth |
|--------|------|------|
| GET | `/api/ping` | Public |
| GET | `/api/health` | Public |
| GET | `/api/setup/seed` | Public (Render only) |
| POST | `/api/auth/register` | Public |
| POST | `/api/auth/login` | Public |
| POST | `/api/auth/login/form` | Public (Swagger; hidden from schema) |
| GET | `/api/auth/me` | JWT |
| GET | `/api/users/` | JWT **admin** |
| POST | `/api/users/` | JWT **admin** |
| GET | `/api/admin/shadow-comparison` | JWT **admin** |
| GET | `/api/admin/stats` | JWT **admin** |
| GET | `/api/admin/all-farms` | JWT **admin** |
| GET | `/api/admin/all-users` | JWT **admin** |
| GET | `/api/admin/activity-feed` | JWT **admin** |
| PUT | `/api/admin/users/{user_id}/role` | JWT **admin** |
| GET | `/api/admin/scan-sessions` | JWT **admin** |
| GET | `/api/admin/scan-sessions/{session_id}` | JWT **admin** |
| GET | `/api/admin/managers-overview` | JWT **admin** |
| GET | `/api/admin/farms-health-comparison` | JWT **admin** |
| GET | `/api/admin/manager-assignments/{manager_id}` | JWT **admin** |
| POST | `/api/admin/assign-manager` | JWT **admin** |
| GET | `/api/admin/daily-digest` | JWT **admin** |
| POST | `/api/admin/daily-digest/send` | JWT **admin** |
| GET | `/api/farms/` | JWT |
| POST | `/api/farms/` | JWT (`manager_id` **admin** only) |
| GET | `/api/farms/{farm_id}/stats` | JWT + farm ACL |
| GET | `/api/farms/{farm_id}/weather` | JWT + farm ACL |
| GET | `/api/farms/{farm_id}` | JWT + farm ACL |
| PUT | `/api/farms/{farm_id}` | JWT + farm ACL |
| DELETE | `/api/farms/{farm_id}` | JWT + farm ACL |
| GET | `/api/detections/model-status` | Public |
| POST | `/api/detections/analyze` | JWT |
| POST | `/api/detections/analyze-batch` | JWT |
| POST | `/api/detections/save-batch` | JWT + farm ACL |
| POST | `/api/detections/analyze-leaf` | JWT |
| POST | `/api/detections/save` | JWT + farm ACL |
| GET | `/api/detections/report` | JWT + farm ACL |
| GET | `/api/detections/{detection_id}/image` | JWT + farm ACL |
| GET | `/api/detections/farm/{farm_id}` | JWT + farm ACL |
| GET | `/api/detections/recent` | JWT |
| GET | `/api/detections/summary/{farm_id}` | JWT + farm ACL |
| GET | `/api/detections/stats` | JWT |
| POST | `/api/scan/analyze-frame` | JWT **farmer / manager / admin** |
| POST | `/api/scan/sessions` | JWT **farmer / manager / admin** |
| GET | `/api/scan/sessions/farm/{farm_id}` | JWT + farm ACL |
| POST | `/api/scan/sessions/{session_id}/detections` | JWT **farmer / manager / admin** |
| POST | `/api/scan/sessions/{session_id}/complete` | JWT **farmer / manager / admin** |
| POST | `/api/scan/sessions/{session_id}/cancel` | JWT **farmer / manager / admin** |
| POST | `/api/scan/sessions/{session_id}/next-zone` | JWT **farmer / manager / admin** |
| POST | `/api/scan/submit-session` | JWT (legacy) |
| GET | `/api/alerts/stats` | JWT |
| GET | `/api/alerts/unread/count` | JWT |
| PUT | `/api/alerts/mark-all-read` | JWT |
| GET | `/api/alerts/farm/{farm_id}` | JWT + farm ACL |
| GET | `/api/alerts/` | JWT |
| PUT | `/api/alerts/{alert_id}/read` | JWT |
| POST | `/api/alerts/{alert_id}/read` | JWT (alias) |
| GET | `/api/alerts/{alert_id}` | JWT |
| GET | `/api/alerts/{alert_id}/image` | JWT |

Non-API (only if `frontend/` exists next to `backend/`): `GET /`, `GET /styles.css`, `GET /app.js`, static mount `/static`.

---

## Shared schemas

### `UserOut`

```json
{
  "id": 1,
  "name": "Ramesh Farmer",
  "email": "farmer@cropguard.ai",
  "role": "farmer",
  "created_at": "2026-01-15T10:00:00"
}
```

### `TokenResponse`

```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "user": { "...UserOut..." }
}
```

### `FarmOut`

```json
{
  "id": 1,
  "user_id": 2,
  "manager_id": 3,
  "name": "Hosahalli Block A",
  "location": "Hosahalli, Karnataka",
  "crop_type": "chrysanthemum",
  "area_acres": 2.5,
  "description": "",
  "created_at": "2026-01-15T10:00:00"
}
```

### `PredictionOut`

```json
{
  "class": "Bacterial",
  "confidence": 88.4,
  "is_problem": true,
  "actual_class": "Bacterial",
  "message": null
}
```

`class` may be `uncertain` when Analysis confidence is **&lt; 75%**. `actual_class` is the raw argmax label. `is_problem` is true only for Bacterial / Septoria (not when rewritten to uncertain).

### `DetectionOut`

```json
{
  "id": 42,
  "farm_id": 1,
  "image_path": "C:\\...\\storage\\uploads\\farm1_....jpg",
  "predicted_class": "Bacterial",
  "confidence": 88.4,
  "timestamp": "2026-08-18T12:00:00",
  "latitude": 12.9716,
  "longitude": 77.5946,
  "plant_zone_id": "zone-3",
  "session_id": 7
}
```

GPS / zone / session are null for Analysis saves; Live Scan fills them.

### `AlertOut`

```json
{
  "id": 9,
  "farm_id": 1,
  "detection_id": 42,
  "class_name": "Bacterial",
  "confidence": 88.4,
  "flagged_image_path": "C:\\...\\storage\\flagged\\ALERT_Bacterial_....jpg",
  "timestamp": "2026-08-18T12:00:00",
  "is_read": false
}
```

### `ScanSessionSummaryOut`

```json
{
  "session_id": 7,
  "farm_id": 1,
  "manager_id": 2,
  "status": "completed",
  "total_scanned": 12,
  "healthy_count": 9,
  "bacterial_count": 2,
  "septoria_count": 1,
  "diseased_count": 0,
  "pest_count": 0,
  "water_stressed_count": 0,
  "flagged_count": 3,
  "started_at": "2026-08-18T11:00:00",
  "completed_at": "2026-08-18T11:20:00"
}
```

`status`: `active` | `completed` | `cancelled`. Legacy count columns stay at 0 on new 3-class sessions. `manager_id` is the user who created the session (farmers included).

`class_counts` objects are `{ "Bacterial": n, "Healthy": n, "Septoria": n }`.

---

## System

### `GET /api/ping`

**Auth:** none.

**Response:** `{ "status": "alive" }`

```bash
curl http://localhost:8001/api/ping
```

### `GET /api/health`

**Auth:** none.

**Response:** live model + shadow v2 + leaf model status.

```json
{
  "status": "ok",
  "service": "CropGuard AI",
  "model": {
    "torch_available": true,
    "loaded": true,
    "path": ".../chrysanthemum_leaf_model.pth",
    "classes": ["Bacterial", "Healthy", "Septoria"],
    "class_to_idx": { "Bacterial": 0, "Healthy": 1, "Septoria": 2 },
    "device": "cpu",
    "shadow_v2": { "loaded": false, "path": null },
    "leaf_model": {
      "loaded": true,
      "path": ".../chrysanthemum_leaf_model.pth",
      "classes": ["Bacterial", "Healthy", "Septoria"],
      "class_to_idx": { "Bacterial": 0, "Healthy": 1, "Septoria": 2 }
    }
  }
}
```

If torch or the `.pth` is missing: `loaded: false` and `error` string.

```bash
curl http://localhost:8001/api/health
```

### `GET /api/setup/seed`

**Auth:** none. **Only runs when `RENDER` is set.** Locally returns `{ "message": "Only runs on Render server" }`.

If `admin@cropguard.ai` already exists: `{ "message": "Already seeded", "status": "ok" }`.

Success creates demo users + two farms.

```bash
curl https://cropguard-ai-backend.onrender.com/api/setup/seed
```

---

## Auth — `/api/auth`

### `POST /api/auth/register`

**Auth:** none. **201** on success.

**Body (`UserRegister`)**

| Field | Type | Rules |
|-------|------|--------|
| `name` | string | 2–120 chars |
| `email` | email | unique |
| `password` | string | 6–128 chars |
| `role` | string | `farmer` (default), `manager`, or `admin` |

**Response:** `TokenResponse`. **400** `Email already registered`.

```bash
curl -s http://localhost:8001/api/auth/register \
  -H "Content-Type: application/json" \
  -d "{\"name\":\"Test Farmer\",\"email\":\"test@example.com\",\"password\":\"secret1\",\"role\":\"farmer\"}"
```

Anyone can register as `admin` today. Do not leave this open on a real tenant.

### `POST /api/auth/login`

**Auth:** none.

**Body (`UserLogin`):** `{ "email": "...", "password": "..." }`

**Response:** `TokenResponse`. **401** `Invalid email or password`.

```bash
curl -s http://localhost:8001/api/auth/login \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"farmer@cropguard.ai\",\"password\":\"farmer123\"}"
```

### `POST /api/auth/login/form`

**Auth:** none. Hidden from `/docs`. OAuth2 form for Swagger Authorize: `username` = email, `password` = password.

```bash
curl -s http://localhost:8001/api/auth/login/form \
  -d "username=farmer@cropguard.ai&password=farmer123"
```

### `GET /api/auth/me`

**Auth:** JWT any role.

**Response:** `UserOut`.

```bash
curl -s http://localhost:8001/api/auth/me \
  -H "Authorization: Bearer $TOKEN"
```

---

## Users — `/api/users`

### `GET /api/users/`

**Auth:** JWT **admin**.

**Response:** `UserOut[]` newest first.

```bash
curl -s http://localhost:8001/api/users/ -H "Authorization: Bearer $ADMIN_TOKEN"
```

### `POST /api/users/`

**Auth:** JWT **admin**. **201**.

**Body:** same as `UserRegister`. **400** if email exists.

```bash
curl -s http://localhost:8001/api/users/ \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"name\":\"New Manager\",\"email\":\"mgr2@cropguard.ai\",\"password\":\"secret1\",\"role\":\"manager\"}"
```

---

## Admin — `/api/admin`

All routes: JWT **admin**. **403** otherwise.

### `GET /api/admin/shadow-comparison`

Live vs shadow-v2 agreement from `storage/shadow_predictions.csv` (gitignored).

```json
{
  "total_predictions": 0,
  "agreements": 0,
  "disagreements": 0,
  "agreement_rate": null,
  "disagreement_breakdown": {},
  "disagreement_pairs": {},
  "shadow_model": { "loaded": false, "path": null },
  "csv_path": ".../shadow_predictions.csv"
}
```

When the CSV has rows, also `agreement_rate_pct`.

### `GET /api/admin/stats`

**Response (`AdminStatsOut`)**

```json
{
  "total_farms": 2,
  "total_users": 2,
  "total_detections": 40,
  "detections_today": 3,
  "most_common_problem": "Bacterial",
  "platform_health_score": 82.5,
  "daily_trends": [
    {
      "date": "2026-08-18",
      "healthy": 10,
      "bacterial": 2,
      "septoria": 1,
      "diseased": 0,
      "pest_affected": 0,
      "water_stressed": 0,
      "total": 13
    }
  ],
  "most_active_farm": "Hosahalli Block A",
  "most_common_disease_today": "Bacterial"
}
```

`total_users` counts farmers + managers only. `daily_trends` is the last 7 days. `platform_health_score` = % of detections classified healthy.

### `GET /api/admin/all-farms`

**Response (`AdminFarmOut[]`):** `id`, `name`, `owner_name`, `owner_email`, `crop_type`, `location`, `last_scan`, `health_score`, `health_status` (`healthy` ≥70, `warning` ≥40, else `critical`).

### `GET /api/admin/all-users`

**Response (`AdminUserOut[]`):** `UserOut` fields plus `farms_count`, `status` (always `"Active"`).

### `GET /api/admin/activity-feed`

**Response:** latest **20** detections as `ActivityFeedItem[]`: `id`, `farm_id`, `farm_name`, `predicted_class`, `confidence`, `timestamp`, `message`.

### `PUT /api/admin/users/{user_id}/role`

**Body (`RoleChangeRequest`):** `{ "role": "farmer" }` or `{ "role": "manager" }`.

**Response:** `AdminUserOut`. **400** if target is admin or role is invalid. **404** if user missing.

```bash
curl -s -X PUT http://localhost:8001/api/admin/users/2/role \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"role\":\"manager\"}"
```

### `GET /api/admin/scan-sessions`

**Query:** `farm_id` (optional int), `manager_id` (optional int), `sort` = `desc` (default) | `asc`.

**Response (`AdminScanSessionOut[]`):** `session_id`, `farm_id`, `farm_name`, `manager_id`, `manager_name`, `started_at`, `completed_at`, `total_scanned`, `issues_found`, `status`.

```bash
curl -s "http://localhost:8001/api/admin/scan-sessions?farm_id=1&sort=desc" \
  -H "Authorization: Bearer $ADMIN_TOKEN"
```

### `GET /api/admin/scan-sessions/{session_id}`

**Response (`AdminScanSessionDetailOut`):** session summary plus `healthy_count`, `bacterial_count`, `septoria_count`, legacy counts, and `flagged_detections[]` (`id`, `predicted_class`, `confidence`, `timestamp`, `latitude`, `longitude`).

**404** `Scan session not found`.

### `GET /api/admin/managers-overview`

**Response (`AdminManagerOverviewOut[]`):** `manager_id`, `manager_name`, `assigned_farms` (names), `assigned_farm_count`, `scans_this_week`, `issues_this_week`, `last_scan_at`. Week = last 7 calendar days.

### `GET /api/admin/farms-health-comparison`

**Response (`AdminFarmHealthComparisonOut[]`):** `farm_id`, `farm_name`, `health_score`, `health_status`, `trend` (`improving` | `worsening` | `stable`), `last_manager_name`, `last_scanned_at`. Trend compares the last two **completed** sessions (±2 health points).

### `GET /api/admin/manager-assignments/{manager_id}`

**Response:** `{ "manager_id": 3, "farm_ids": [1, 2] }`. **404** `Manager not found`.

### `POST /api/admin/assign-manager`

**Body (`ManagerAssignRequest`):** `{ "manager_id": 3, "farm_ids": [1, 2] }` — **replaces** existing assignments.

**Response:** `{ "manager_id": 3, "assigned_farm_ids": [1, 2], "message": "Assigned 2 farm(s) to …" }`

**400** invalid manager or farm id.

```bash
curl -s http://localhost:8001/api/admin/assign-manager \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"manager_id\":3,\"farm_ids\":[1,2]}"
```

### `GET /api/admin/daily-digest`

Last **24 hours** of scan sessions (`AdminDailyDigestOut`): `period_start`, `period_end`, `farms_scanned`, `managers_active`, `total_sessions`, `total_plants_checked`, `total_issues_found`, `breakdown_by_farm[]`, `top_concerning_farms[]`, `manager_names[]`.

Farm breakdown row: `farm_id`, `farm_name`, `sessions_count`, `plants_scanned`, `issues_found`, `problem_rate`.

### `POST /api/admin/daily-digest/send`

Same digest, then emails all admin users if SMTP is configured.

**Response (`DailyDigestSendOut`):** `{ "digest": {…}, "email_sent": false, "admin_recipients": 1, "message": "…" }`

---

## Farms — `/api/farms`

All require JWT. Farm-scoped routes use farm ACL.

### `GET /api/farms/`

**Response:** `FarmOut[]` newest first (ACL-filtered).

### `POST /api/farms/`

**201.** **Body (`FarmCreate`)**

| Field | Type | Default |
|-------|------|---------|
| `name` | string 2–120 | required |
| `location` | string | `""` |
| `crop_type` | string | `"chrysanthemum"` |
| `area_acres` | float ≥ 0 | `0` |
| `description` | string | `""` |
| `manager_id` | int \| null | `null` |

Setting `manager_id` as non-admin → **403** `Only admin can assign a manager`. Owner is always the caller (`user_id`).

```bash
curl -s http://localhost:8001/api/farms/ \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"name\":\"Block C\",\"location\":\"Hosahalli\",\"crop_type\":\"chrysanthemum\",\"area_acres\":1.5}"
```

### `GET /api/farms/{farm_id}`

**Response:** `FarmOut`.

### `GET /api/farms/{farm_id}/stats`

**Response (`FarmStatsOut`):** `farm_id`, `total_detections`, `problems_found`, `last_scan`, `health_score` (% healthy), `class_counts`.

### `GET /api/farms/{farm_id}/weather`

Open-Meteo for **fixed default lat/lon** (not geocoded from `farm.location`). Cached ~60 minutes.

**Response (`FarmWeatherOut`):** `farm_id`, `farm_name`, `latitude`, `longitude`, `temperature`, `humidity`, `rainfall`, `windspeed`, `disease_risk` (`LOW` | `MEDIUM` | `HIGH`), `updated_at`, `cached`, `note`.

**503** if weather fetch fails with no fallback.

### `PUT /api/farms/{farm_id}`

**Body (`FarmUpdate`):** any subset of `name`, `location`, `crop_type`, `area_acres`, `description`. Omits `manager_id` (use admin assign).

**Response:** `FarmOut`.

### `DELETE /api/farms/{farm_id}`

**204** empty body. Farmer may only delete farms they own (`user_id`); otherwise **403**.

```bash
curl -s -X DELETE http://localhost:8001/api/farms/1 \
  -H "Authorization: Bearer $TOKEN"
```

---

## Detections — `/api/detections`

Uses `ai_engine` (75% uncertain gate) except `analyze-leaf` (`leaf_engine`, no 75% rewrite). Saving a problem with confidence **&gt; 70** creates an Alert. WhatsApp fires if not healthy and confidence **&gt; 80**.

### `GET /api/detections/model-status`

**Auth:** none.

```json
{
  "loaded": true,
  "path": ".../chrysanthemum_leaf_model.pth",
  "classes": ["Bacterial", "Healthy", "Septoria"],
  "class_to_idx": { "Bacterial": 0, "Healthy": 1, "Septoria": 2 }
}
```

Unloaded: `{ "loaded": false, "path": null }` (or path without `classes` if the file exists but failed to load).

### `POST /api/detections/analyze`

**Auth:** JWT. **multipart:** `file` (required). **Does not write to the DB.**

**Response (`AnalysisPreviewOut`)**

```json
{
  "prediction": {
    "class": "Healthy",
    "confidence": 96.2,
    "is_problem": false,
    "actual_class": "Healthy",
    "message": null
  },
  "message": "Detected Healthy (96.2%)",
  "analyzed_at": "2026-08-18T14:00:00"
}
```

**400** bad/empty/oversize file. **503** model load error.

```bash
curl -s http://localhost:8001/api/detections/analyze \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@leaf.jpg"
```

### `POST /api/detections/analyze-batch`

**Auth:** JWT. **multipart:** `files` (repeat the field). Max **100** images. Per-file errors do not abort the batch.

**Response (`BatchAnalysisOut`):** `total_images`, `success_count`, `failed_count`, `class_counts`, `class_percentages`, `results[]` (`filename` + `prediction`), `errors[]` (`filename`, `error`), `message`, `analyzed_at`.

```bash
curl -s http://localhost:8001/api/detections/analyze-batch \
  -H "Authorization: Bearer $TOKEN" \
  -F "files=@a.jpg" -F "files=@b.jpg"
```

### `POST /api/detections/save-batch`

**Auth:** JWT + farm ACL. **201.**

**multipart:** `farm_id` (form int), `files` (list). Analyzes **and** persists each image; may create alerts / WhatsApp.

**Response (`BatchSaveOut`):** `farm_id`, `total_images`, `saved_count`, `failed_count`, `alert_count`, `class_counts`, `class_percentages`, `errors[]`, `message`, `saved_at`.

```bash
curl -s http://localhost:8001/api/detections/save-batch \
  -H "Authorization: Bearer $TOKEN" \
  -F "farm_id=1" -F "files=@a.jpg" -F "files=@b.jpg"
```

### `POST /api/detections/analyze-leaf`

**Auth:** JWT. **multipart:** `file`. Leaf Scan page. **No 75% uncertain rewrite.** Same weights as Analysis.

**Response (`LeafAnalysisOut`)**

```json
{
  "class": "Septoria",
  "confidence": 91.3,
  "is_problem": true,
  "description": "Septoria leaf spot detected (fungal disease).",
  "recommendation": "Apply appropriate fungicide. Improve air circulation. Remove and destroy affected leaves. Avoid wetting foliage.",
  "message": null
}
```

If the leaf model is down: `"class": "unavailable"`, `"message": "Leaf model not loaded"`.

### `POST /api/detections/save`

**Auth:** JWT + farm ACL. **201.** Persists a **client-confirmed** result (does not re-run the model).

**multipart**

| Field | Type |
|-------|------|
| `farm_id` | int |
| `predicted_class` | string (normalized: diseased → Bacterial, etc.) |
| `confidence` | float |
| `file` | image |

**Response (`DetectionResult`):** `{ "detection": DetectionOut, "prediction": PredictionOut, "alert_created": true, "message": "ALERT: …" }`

```bash
curl -s http://localhost:8001/api/detections/save \
  -H "Authorization: Bearer $TOKEN" \
  -F "farm_id=1" -F "predicted_class=Bacterial" -F "confidence=88.4" -F "file=@leaf.jpg"
```

### `GET /api/detections/report`

**Auth:** JWT + farm ACL.

**Query:** `farm_id` (required), `from` (date `YYYY-MM-DD`), `to` (date). **400** if `to` &lt; `from`.

**Response (`FarmReportOut`):** `summary` (`farm_id`, `farm_name`, `crop_type`, `location`, `period_from`, `period_to`, `generated_at`, `total_detections`, `health_score`, `class_counts`, `class_percentages`), `detections[]` (`id`, `farm_id`, `predicted_class`, `confidence`, `timestamp`, `status` = `Active` | `Resolved`), `recommendations` (plain text).

Healthy rows are `Resolved`. Problem rows are `Active` only if a linked unread alert exists.

```bash
curl -s "http://localhost:8001/api/detections/report?farm_id=1&from=2026-08-01&to=2026-08-18" \
  -H "Authorization: Bearer $TOKEN"
```

### `GET /api/detections/{detection_id}/image`

**Auth:** JWT + farm ACL. **FileResponse** of the stored image. **404** if record or file missing.

```bash
curl -s -o det.jpg http://localhost:8001/api/detections/42/image \
  -H "Authorization: Bearer $TOKEN"
```

### `GET /api/detections/farm/{farm_id}`

**Response:** `DetectionOut[]` newest first.

### `GET /api/detections/recent`

**Auth:** JWT. Last **20** detections across accessible farms.

### `GET /api/detections/summary/{farm_id}`

**Response:** `{ "farm_id": 1, "total_detections": 12, "class_counts": { "Bacterial": 2, "Healthy": 9, "Septoria": 1 } }`

### `GET /api/detections/stats`

Dashboard totals for accessible farms: `{ "total_farms", "total_detections", "total_alerts", "unread_alerts", "class_counts" }`.

---

## Live Scan — `/api/scan`

Walk flow: **create session → analyze-frame (no DB) → bulk detections → complete**. **Cancel** on discard. Do not use `submit-session` from the current SPA.

`analyze-frame` / session mutate routes: JWT **farmer, manager, or admin**. Listing sessions: any JWT with farm ACL.

Frames are **center-cropped (~70%)** then run through `ai_engine` (including the 75% uncertain gate). Smoothing is **in-process RAM** keyed by `session_id` (not multi-worker safe). Max frame **10 MB**. Bulk max **200** items.

### `POST /api/scan/analyze-frame`

**multipart**

| Field | Type | Notes |
|-------|------|--------|
| `file` | image | required |
| `farm_id` | int | optional; ACL-checked |
| `session_id` | int | if set, session must be `active` and match `farm_id` |
| `latitude` | float | optional GPS |
| `longitude` | float | optional GPS |

**No database writes.** With `session_id`, majority smoothing (~3 frames, ≥70%) sets `smoothed_class`, `is_problem` (confirmed problem only), and `plant_zone_id`.

**Response (`ScanFrameAnalyzeOut`)**

```json
{
  "class": "Bacterial",
  "confidence": 84.1,
  "is_problem": true,
  "actual_class": "Bacterial",
  "smoothed_class": "Bacterial",
  "latitude": 12.9716,
  "longitude": 77.5946,
  "plant_zone_id": "z-1",
  "analyzed_at": "2026-08-18T14:05:00"
}
```

**400** empty/too-large frame, session not active, farm/session mismatch. **404** session missing. **503** model down.

```bash
curl -s http://localhost:8001/api/scan/analyze-frame \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@frame.jpg" -F "farm_id=1" -F "session_id=7" \
  -F "latitude=12.9716" -F "longitude=77.5946"
```

### `POST /api/scan/sessions`

**Body:** `{ "farm_id": 1, "started_at": "2026-08-18T14:00:00" }` (`started_at` optional).

Cancels this user’s other `active` sessions. Stale actives (&gt; 6 hours) are cancelled.

**Response:** `{ "session_id": 7 }`

```bash
curl -s http://localhost:8001/api/scan/sessions \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"farm_id\":1}"
```

### `GET /api/scan/sessions/farm/{farm_id}`

**Auth:** JWT + farm ACL (farmers can list).

**Response:** `ScanSessionSummaryOut[]` newest first.

### `POST /api/scan/sessions/{session_id}/detections`

**Body (`ScanBulkDetectionsIn`)**

```json
{
  "detections": [
    {
      "class": "Bacterial",
      "confidence": 88.4,
      "timestamp": "2026-08-18T14:10:00",
      "lat": 12.9716,
      "lon": 77.5946,
      "image_base64": "data:image/jpeg;base64,/9j/4AAQ...",
      "plant_zone_id": "z-1"
    }
  ]
}
```

`class` alias: `predicted_class`. Skips `uncertain` / `unavailable`. **One problem row per plant zone** (needs `image_base64` and confidence **&gt; 70**). Healthy rows save if they include image bytes. WhatsApp is dispatched on a background thread after commit.

If the session is already `completed`, returns `{ "saved_count": 0, "flagged_count": <existing> }` (idempotent). Other non-active → **400**. Over 200 items → **400**.

**Response:** `{ "saved_count": 3, "flagged_count": 2 }`

### `POST /api/scan/sessions/{session_id}/complete`

Marks `completed`, clears smoothing RAM, emails admin completion report if SMTP is set.

**Response:** `ScanSessionSummaryOut`. Already completed → same summary (idempotent). Cancelled → **400**.

```bash
curl -s -X POST http://localhost:8001/api/scan/sessions/7/complete \
  -H "Authorization: Bearer $TOKEN"
```

### `POST /api/scan/sessions/{session_id}/cancel`

Marks `cancelled` if still `active`; otherwise returns current summary (no error). No completion email.

### `POST /api/scan/sessions/{session_id}/next-zone`

Manual “next plant” when GPS is weak. Session must be `active`.

**Response:** `{ "session_id": 7, "plant_zone_id": "z-2" }`

### `POST /api/scan/submit-session` (legacy)

**Auth:** JWT any role + farm ACL. Does **not** create a `ScanSession`, GPS, or zone. Live Scan must not call this.

**Body (`ScanSessionIn`)**

```json
{
  "farm_id": 1,
  "detections": [
    {
      "predicted_class": "Healthy",
      "actual_class": "Healthy",
      "confidence": 90.0,
      "latitude": null,
      "longitude": null,
      "timestamp": "2026-08-18T14:00:00",
      "image_base64": "/9j/..."
    }
  ]
}
```

**Response:** `{ "message": "Live scan session saved", "detections_saved": 1, "alerts_created": 0, "farm_id": 1 }`

---

## Alerts — `/api/alerts`

JWT; lists are ACL-filtered. Class filters accept legacy names (`diseased` → Bacterial, `water` → Septoria).

### `GET /api/alerts/stats`

**Response:** `{ "date": "2026-08-18", "total_today": 2, "unread": 4, "total_week": 11, "class_counts": { "Bacterial": 2 } }`

`class_counts` is **today only** and uses stored `class_name` strings (may include legacy labels).

### `GET /api/alerts/unread/count`

**Response:** `{ "count": 4 }`

### `PUT /api/alerts/mark-all-read`

No body. **Response:** `{ "updated": 4 }` (integer count).

```bash
curl -s -X PUT http://localhost:8001/api/alerts/mark-all-read \
  -H "Authorization: Bearer $TOKEN"
```

### `GET /api/alerts/farm/{farm_id}`

**Response:** `AlertOut[]` newest first.

### `GET /api/alerts/`

**Query:** `filter` default `all`. Also: `unread`, `bacterial`, `septoria`, `healthy`, `diseased`, `pest`, `water`.

```bash
curl -s "http://localhost:8001/api/alerts/?filter=unread" \
  -H "Authorization: Bearer $TOKEN"
```

### `PUT /api/alerts/{alert_id}/read` and `POST /api/alerts/{alert_id}/read`

No body. Sets `is_read: true`. **Response:** `AlertOut`. **404** / **403** if missing or not in ACL.

### `GET /api/alerts/{alert_id}`

**Response:** `AlertOut`.

### `GET /api/alerts/{alert_id}/image`

**FileResponse** of `flagged_image_path`. **404** if file missing.

```bash
curl -s -o alert.jpg http://localhost:8001/api/alerts/9/image \
  -H "Authorization: Bearer $TOKEN"
```

---

## Typical client sequences

**Login + list farms + analyze + save**

```bash
TOKEN=$(curl -s http://localhost:8001/api/auth/login \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"farmer@cropguard.ai\",\"password\":\"farmer123\"}" \
  | python -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

curl -s http://localhost:8001/api/farms/ -H "Authorization: Bearer $TOKEN"

curl -s http://localhost:8001/api/detections/analyze \
  -H "Authorization: Bearer $TOKEN" -F "file=@leaf.jpg"

curl -s http://localhost:8001/api/detections/save \
  -H "Authorization: Bearer $TOKEN" \
  -F "farm_id=1" -F "predicted_class=Healthy" -F "confidence=96.2" -F "file=@leaf.jpg"
```

**Live Scan walk**

```bash
# 1. create
# POST /api/scan/sessions  { "farm_id": 1 }  → session_id
# 2. loop
# POST /api/scan/analyze-frame  file + session_id + farm_id + lat/lon
# 3. optional
# POST /api/scan/sessions/{id}/next-zone
# 4. persist confirmed frames
# POST /api/scan/sessions/{id}/detections
# 5. finish
# POST /api/scan/sessions/{id}/complete
# or discard
# POST /api/scan/sessions/{id}/cancel
```

---

## Source map

| Prefix | File |
|--------|------|
| `/api/ping`, `/api/health`, `/api/setup/seed` | `backend/main.py` |
| `/api/auth`, `/api/users`, `/api/admin` | `backend/routers/users.py` |
| `/api/farms` | `backend/routers/farms.py` |
| `/api/detections` | `backend/routers/detections.py` |
| `/api/scan` | `backend/routers/scan.py` |
| `/api/alerts` | `backend/routers/alerts.py` |
| Pydantic models | `backend/schemas.py` |
| JWT / ACL | `backend/auth.py` |
