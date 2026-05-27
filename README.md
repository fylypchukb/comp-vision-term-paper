# Gesture Smart Lock — Full System Description

> **Scope:** Complete technical reference for all system logic, architecture, gesture definitions,
> data flows, API contracts, and design decisions. Written for developers and reviewers.

---

## Table of Contents

1. [System Overview](#1-system-overview)
2. [High-Level Architecture](#2-high-level-architecture)
3. [CV Module](#3-cv-module)
   - 3.1 [Entry Point & Configuration](#31-entry-point--configuration)
   - 3.2 [Hand Detection — MediaPipe Wrapper](#32-hand-detection--mediapipe-wrapper)
   - 3.3 [Gesture Classifier — Rule-Based Recognition](#33-gesture-classifier--rule-based-recognition)
   - 3.4 [Gesture Buffer — Temporal State Machine](#34-gesture-buffer--temporal-state-machine)
4. [Gesture Catalog](#4-gesture-catalog)
   - 4.1 [Finger State Model](#41-finger-state-model)
   - 4.2 [All 11 Recognized Gestures](#42-all-11-recognized-gestures)
   - 4.3 [Classification Priority Order](#43-classification-priority-order)
   - 4.4 [Deliberately Excluded Gestures](#44-deliberately-excluded-gestures)
5. [Backend — FastAPI Service](#5-backend--fastapi-service)
   - 5.1 [Application Bootstrap](#51-application-bootstrap)
   - 5.2 [Database Layer](#52-database-layer)
   - 5.3 [ORM Models](#53-orm-models)
   - 5.4 [Service Layer](#54-service-layer)
   - 5.5 [REST API Endpoints](#55-rest-api-endpoints)
   - 5.6 [WebSocket Events](#56-websocket-events)
6. [Frontend — React Dashboard](#6-frontend--react-dashboard)
   - 6.1 [Routing & Page Structure](#61-routing--page-structure)
   - 6.2 [Global State & WebSocket (AppContext)](#62-global-state--websocket-appcontext)
   - 6.3 [Pages](#63-pages)
   - 6.4 [UI Components](#64-ui-components)
7. [End-to-End Data Flows](#7-end-to-end-data-flows)
   - 7.1 [PIN Entry Flow (gesture unlock)](#71-pin-entry-flow-gesture-unlock)
   - 7.2 [PIN Recording Flow (setting a new PIN)](#72-pin-recording-flow-setting-a-new-pin)
   - 7.3 [Manual Lock/Unlock from Dashboard](#73-manual-lockunlock-from-dashboard)
8. [PIN Comparison Algorithm](#8-pin-comparison-algorithm)
9. [Database Schema](#9-database-schema)
10. [Configuration Reference](#10-configuration-reference)
11. [Deployment — Docker Compose](#11-deployment--docker-compose)
12. [Non-Functional Characteristics](#12-non-functional-characteristics)
13. [Design Decisions & Trade-offs](#13-design-decisions--trade-offs)
14. [Developer & Evaluation Tools](#14-developer--evaluation-tools)
    - 14.1 [collect_dataset.py — Evaluation Dataset Collector](#141-collect_datasetpy--evaluation-dataset-collector)
    - 14.2 [capture_visuals.py — Annotated Screenshot Tool](#142-capture_visualspy--annotated-screenshot-tool)
    - 14.3 [evaluate.py — Metrics Calculator & Performance Benchmark](#143-evaluatepy--metrics-calculator--performance-benchmark)

---

## 1. System Overview

**Gesture Smart Lock** is a three-tier computer-vision access control system:

| Layer | Technology | Role |
|---|---|---|
| **CV Module** | Python · OpenCV · MediaPipe | Captures camera frames, classifies hand gestures, accumulates a PIN sequence, POSTs each confirmed gesture to the backend |
| **Backend** | Python · FastAPI · SQLAlchemy · SQL Server | Persists lock/user/PIN data, verifies gesture sequences, toggles lock state, pushes real-time events over WebSocket |
| **Frontend** | TypeScript · React · Vite | Admin dashboard — live gesture feedback, PIN recording, manual lock control, event log |

The system replaces a numeric PIN keypad with a sequence of **hand gestures** (e.g. ✋ → ✊ → ☝️).
A user holds each gesture stable in front of a webcam for **15 frames** (~0.75 s at 20 FPS);
when the full sequence matches the stored PIN the lock toggles state.

---

## 2. High-Level Architecture

```
┌──────────────────────────────────────────────────────────────┐
│  CAMERA                                                      │
│    │  BGR frame (640×480 @ 20 FPS)                           │
│    ▼                                                         │
│  HandDetector (MediaPipe)                                    │
│    │  HandLandmarks: 21 (x,y,z) points                       │
│    ▼                                                         │
│  GestureClassifier (rule-based geometry)                     │
│    │  gesture: str | None                                    │
│    ▼                                                         │
│  GestureBuffer (temporal state machine)                      │
│    │  after 15 stable frames → HTTP POST /api/gestures/verify│
│    ▼                                                         │
└────────────────── CV MODULE ─────────────────────────────────┘
          │ REST (requests)        ▲ poll GET /api/locks/{id}/mode
          ▼                        │   every 2 s (background thread)
┌──────────────────────────────────────────────────────────────┐
│  FastAPI (uvicorn, async)                                    │
│    ├── routers/gestures.py  POST /api/gestures/verify        │
│    ├── routers/locks.py     CRUD + state + mode + PIN        │
│    ├── routers/users.py     CRUD                             │
│    └── /ws                  WebSocket broadcast              │
│                                                              │
│  SQLAlchemy (async) ──► Microsoft SQL Server 2022            │
│    tables: users, locks, pin_configs, lock_states, access_log│
└──────────────────── BACKEND ─────────────────────────────────┘
          │ WebSocket (ws://)      │ REST (fetch)
          ▼                        ▼
┌──────────────────────────────────────────────────────────────┐
│  React SPA (Vite + TypeScript)                               │
│    ├── Dashboard      — lock grid, live gesture overlay      │
│    ├── LockDetail     — mode switch, PIN record/save/reset   │
│    ├── Users          — user CRUD                            │
│    └── EventLog       — full access log with filters         │
└──────────────────── FRONTEND ────────────────────────────────┘
```

All three services run in Docker Compose. The CV module requires direct camera
access, so on **Windows/macOS hosts** it is run natively while the rest of the stack
runs inside containers.

---

## 3. CV Module

**Location:** `cv-module/`

### 3.1 Entry Point & Configuration

**File:** `cv-module/main.py`

#### Environment Variables

| Variable | Type | Default | Description |
|---|---|---|---|
| `BACKEND_URL` | str | `http://localhost:8000` | FastAPI base URL |
| `CAMERA_INDEX` | int | `0` | OpenCV camera index |
| `LOCK_ID` | int | `1` | Which lock this CV instance controls |
| `DETECTION_CONFIDENCE` | float | `0.7` | MediaPipe detection threshold |
| `TRACKING_CONFIDENCE` | float | `0.5` | MediaPipe tracking threshold |
| `DEBUG_DISPLAY` | bool | `false` | Show annotated camera window |
| `REQUEST_TIMEOUT` | float | `2.0` | HTTP request timeout (seconds) |
| `MODE_POLL_INTERVAL` | float | `2.0` | How often to poll the backend for mode changes |

#### Camera Loop (`main()`)

```
Startup
  ├── OpenCV VideoCapture (640×480, 30 FPS cap)
  ├── HandDetector, GestureClassifier, GestureBuffer instantiated
  └── Mode-poll background thread started

Per-frame (target 20 FPS, sleep remainder of frame budget):
  1. cap.read()  →  BGR frame
  2. HandDetector.process_frame()  →  HandLandmarks | None + annotated frame
  3. GestureClassifier.classify()  →  gesture string | None
  4. GestureBuffer.update()        →  ui_state dict
  5. Consume mode change from background poll thread (if any)
  6. [DEBUG_DISPLAY] draw overlay + imshow

Shutdown (SIGINT / SIGTERM / 'q' key / too many frame failures):
  └── release camera, close MediaPipe, destroy windows
```

**Frame failure tolerance:** up to `MAX_READ_FAILURES = 30` consecutive failures before exit.

**Background mode-poll thread:** Runs `GET /api/locks/{lock_id}/mode` every
`MODE_POLL_INTERVAL` seconds independently of the camera loop. The result is
placed in a shared dict; the main loop consumes it and calls `buffer.set_mode()`.
This ensures mode switches from the frontend propagate within ~2 seconds without
blocking frame capture.

**Debug overlay** (`DEBUG_DISPLAY=true`) draws on the annotated frame:
```
Gesture: FIST  (12/15)
Sequence: OPEN_PALM > FIST
Status: collecting   Mode: entry
FPS: 19.8
```

---

### 3.2 Hand Detection — MediaPipe Wrapper

**File:** `cv-module/modules/hand_detector.py`

```python
@dataclass
class HandLandmarks:
    points: list[tuple[float, float, float]]  # 21 landmarks, each (x, y, z) in [0,1]
    handedness: str                            # 'Left' or 'Right'
```

`HandDetector` wraps `mediapipe.solutions.hands` and exposes a single method:

```python
def process_frame(frame: np.ndarray) -> tuple[HandLandmarks | None, np.ndarray]
```

- Input: raw **BGR** frame from OpenCV
- Output: `HandLandmarks` (or `None` if no hand detected) + a copy of the frame with the MediaPipe skeleton drawn
- `max_num_hands = 1` — only the first detected hand is used

**MediaPipe Landmark Topology (21 points):**

```
Index  Name
 0     WRIST
 1-4   THUMB  (CMC → MCP → IP → TIP)
 5-8   INDEX  (MCP → PIP → DIP → TIP)
 9-12  MIDDLE (MCP → PIP → DIP → TIP)
13-16  RING   (MCP → PIP → DIP → TIP)
17-20  PINKY  (MCP → PIP → DIP → TIP)
```

All coordinates are **normalized to [0.0, 1.0]** relative to image size.
`y` increases downward (standard image convention).

---

### 3.3 Gesture Classifier — Rule-Based Recognition

**File:** `cv-module/modules/gesture_classifier.py`

The classifier is **purely geometric** — no machine learning model is loaded.
It operates on a single frame's 21 landmark snapshot.

#### `_finger_states()` — Extended / Curled Detection

Returns a dict `{thumb, index, middle, ring, pinky} → bool`.

| Finger | Axis | Extended when |
|---|---|---|
| Index, Middle, Ring, Pinky | **Y** | `TIP.y < PIP.y` (tip above PIP in screen space) |
| Thumb (Right hand) | **X** | `TIP.x < IP.x` (tip further left) |
| Thumb (Left hand) | **X** | `TIP.x > IP.x` (tip further right) |

#### Tunable Thresholds (constants at top of file)

| Constant | Value | Used for |
|---|---|---|
| `OK_DISTANCE_THRESHOLD` | `0.05` | Euclidean distance between index tip and thumb tip (OK circle) |
| `THUMB_VERTICAL_THRESHOLD` | `0.04` | Y-axis gap between THUMB_TIP and THUMB_MCP |
| `VULCAN_SPREAD_THRESHOLD` | `0.08` | Minimum X gap between MIDDLE_TIP and RING_TIP |
| `VULCAN_PAIR_THRESHOLD` | `0.05` | Maximum X gap within each finger pair (index+middle, ring+pinky) |
| `FINGER_GUN_THUMB_THRESHOLD` | `0.05` | `MIDDLE_MCP.y − THUMB_TIP.y` must exceed this for raised-thumb check |

---

### 3.4 Gesture Buffer — Temporal State Machine

**File:** `cv-module/modules/gesture_buffer.py`

The buffer converts single-frame gesture classifications into a **confirmed PIN sequence**
using a three-state machine and then communicates with the backend.

#### Tuning Constants

| Constant | Value | Meaning |
|---|---|---|
| `REQUIRED_STABLE_FRAMES` | `15` | Frames the same gesture must appear consecutively to confirm it (~0.75 s at 20 FPS) |
| `COOLDOWN_SECONDS` | `2.0` | Pause after each confirmed gesture before accepting another |
| `INACTIVITY_TIMEOUT_SECONDS` | `10.0` | If no gesture is confirmed for 10 s, the accumulated sequence is discarded |
| `MIN_PIN_LENGTH` | `3` | Minimum PIN length (enforced at save, not here) |
| `MAX_PIN_LENGTH` | `6` | Maximum PIN length (enforced at save) |

#### Internal State Machine

```
States: idle | collecting | cooldown

idle ──(gesture appears)──────────────────────────────► collecting
collecting ──(same gesture, count < 15)───────────────► collecting  (increment counter)
collecting ──(gesture changes or disappears)──────────► idle / collecting(new gesture)
collecting ──(count reaches 15)───────────────────────► [confirm gesture] ──► cooldown
cooldown ──(2 seconds elapse)─────────────────────────► idle
```

#### Gesture Confirmation (`_confirm_gesture`)

When `stable_count` reaches 15:
1. Append gesture to `_sequence`
2. Update `_last_confirmed_at` (resets inactivity timer)
3. HTTP POST to `/api/gestures/verify` with full payload
4. Handle server response (`partial` / `match` / `fail` / `recorded`)
5. Enter `cooldown` state for 2 seconds (regardless of server response)

#### HTTP Payload to Backend

```json
{
  "lock_id": 1,
  "gesture": "FIST",
  "sequence": ["OPEN_PALM", "FIST"],
  "mode": "entry",
  "timestamp": "2024-01-15T10:30:00+00:00"
}
```

#### Server Response Handling

| Status | CV Module Action |
|---|---|
| `"partial"` | Continue accumulating — sequence kept |
| `"match"` | Call `reset_sequence()` |
| `"fail"` | Call `reset_sequence()` |
| `"recorded"` | Log the count (recording mode — sequence keeps growing) |

#### `update()` Return Value (UI State Dict)

```python
{
    "current_gesture":      str | None,
    "stable_frames":        int,        # 0–15
    "sequence":             list[str],  # accumulated so far
    "mode":                 str,        # "entry" | "recording"
    "status":               str,        # "idle" | "collecting" | "cooldown" | "confirmed"
    "last_server_response": dict | None,
}
```

---

## 4. Gesture Catalog

### 4.1 Finger State Model

Each gesture is defined by the **extended/curled state** of up to 5 fingers, plus
optional geometric checks (distance, spread angle) on specific landmark coordinates.

```
Notation:  ✓ = extended   ✗ = curled   * = don't care
```

### 4.2 All 11 Recognized Gestures

| Code | Emoji | Label | Thumb | Index | Middle | Ring | Pinky | Extra condition |
|---|---|---|---|---|---|---|---|---|
| `OPEN_PALM` | ✋ | Open Palm | ✓ | ✓ | ✓ | ✓ | ✓ | — |
| `FIST` | ✊ | Fist | * | ✗ | ✗ | ✗ | ✗ | — |
| `INDEX_UP` | ☝️ | Index Up | ✗ | ✓ | ✗ | ✗ | ✗ | — |
| `PEACE` | ✌️ | Peace | ✗ | ✓ | ✓ | ✗ | ✗ | — |
| `THREE` | 🤟 | Three | ✗ | ✓ | ✓ | ✓ | ✗ | — |
| `FOUR` | 🖖 | Four | ✗ | ✓ | ✓ | ✓ | ✓ | — |
| `PINKY_UP` | 🤙 | Pinky Up | ✗ | ✗ | ✗ | ✗ | ✓ | — |
| `OK` | 👌 | OK | * | * | ✓ | ✓ | ✓ | `dist(THUMB_TIP, INDEX_TIP) < 0.05` |
| `ROCK` | 🤘 | Rock | ✗ | ✓ | ✗ | ✗ | ✓ | — |
| `VULCAN` | 🖖 | Vulcan | * | ✓ | ✓ | ✓ | ✓ | `\|MIDDLE_TIP.x − RING_TIP.x\| > 0.08` AND `\|INDEX_TIP.x − MIDDLE_TIP.x\| < 0.05` AND `\|RING_TIP.x − PINKY_TIP.x\| < 0.05` |
| `FINGER_GUN` | 🫵 | Finger Gun | raised | ✓ | ✗ | ✗ | ✗ | `MIDDLE_MCP.y − THUMB_TIP.y > 0.05` |

**Notes on specific gestures:**

- **FIST:** Thumb state is *ignored* — a real fist can have the thumb tucked, pointing sideways, or resting in many positions. The four main fingers being curled is sufficient.
- **OK:** Must be checked before `OPEN_PALM` in priority order because OK has three extended fingers that would otherwise satisfy the open-palm rule without the circle-distance gate. Thumb state is also `*` for the same reason.
- **VULCAN (Star Trek salute):** All four fingers extended with a specific wide split *between* middle and ring (≥ 0.08 normalized), while the index+middle pair and the ring+pinky pair each remain close (< 0.05). Prevents a casually spread FOUR from triggering Vulcan.
- **FINGER_GUN:** Index extended, middle/ring/pinky curled, thumb raised above the knuckle line. The reference point is `MIDDLE_MCP` (the middle-finger knuckle at the top of the closed fist); a resting thumb in INDEX_UP sits at or below that line, while a gun-pose thumb is clearly above it.

### 4.3 Classification Priority Order

The classifier checks each gesture top-to-bottom; **first match wins**.

```
 1. OK           ← must beat OPEN_PALM (3 open fingers + circle)
 2. VULCAN       ← must beat OPEN_PALM (4 open fingers + spread gate)
 3. OPEN_PALM
 4. FIST
 5. FINGER_GUN   ← must beat INDEX_UP (gun thumb triggers same finger states)
 6. INDEX_UP
 7. PEACE
 8. THREE
 9. FOUR         ← after VULCAN (same 4 fingers, no spread check)
10. PINKY_UP
11. ROCK
```

### 4.4 Deliberately Excluded Gestures

| Removed Gesture | Reason |
|---|---|
| `THUMBS_UP` | Indistinguishable from FIST with Y/X axis checks — a raised thumb in a fist-like pose still triggers |
| `THUMBS_DOWN` | Requires inverted-hand detection; inverting the Y axis makes curled fingers read as extended → OPEN_PALM false positives |
| `CALL_ME` (thumb + pinky) | Hand tilt causes pinky Y-check to flip and read as FIST |

---

## 5. Backend — FastAPI Service

**Location:** `backend/`

### 5.1 Application Bootstrap

**File:** `backend/main.py`

1. **Lifespan handler** (`@asynccontextmanager`):
   - *Startup:* calls `init_db()` (creates all tables with up to 10 retries × 3 s delay)
   - *Shutdown:* disposes the SQLAlchemy connection pool
2. **CORS middleware** — allows the configured `CORS_ORIGIN` (default `http://localhost:5173`)
3. **Router registration:** `/api/locks`, `/api/users`, `/api/gestures` + `/api/access-log`
4. **WebSocket endpoint** at `/ws` — receive-only (frontend never sends)
5. **Global SQLAlchemy error handler** → HTTP 503

#### Health Check

```
GET /health  →  {"status": "ok"}
```

---

### 5.2 Database Layer

**File:** `backend/database.py`

- **Dialect:** `mssql+aioodbc` (Microsoft SQL Server via ODBC Driver 18)
- **Auth modes:**
  - **Windows Authentication** (`DB_TRUSTED_CONNECTION=yes`) — for local dev with a named instance (no port needed; SQL Server Browser resolves it)
  - **SQL Server Auth** — `DB_USER` + `DB_PASSWORD` — for Docker / remote
- **`expire_on_commit=False`** — prevents `MissingGreenlet` errors when accessing ORM attributes after `await` in async context
- **`init_db()`** — retry loop: up to 10 attempts with 3-second delays (handles Docker SQL Server cold start ~30 s)
- **`TrustServerCertificate=yes`** — silences cert errors for self-signed / local certificates (mandatory for ODBC Driver 18 which enables encryption by default)

---

### 5.3 ORM Models

**File:** `backend/models/orm.py`

#### `users`

| Column | Type | Constraints |
|---|---|---|
| `id` | INT PK | Auto-increment |
| `username` | VARCHAR(100) | UNIQUE, NOT NULL |
| `role` | VARCHAR(20) | CHECK: `'admin'` or `'operator'`; default `'operator'` |
| `created_at` | DATETIME | Server default: `now()` |

#### `locks`

| Column | Type | Constraints |
|---|---|---|
| `id` | INT PK | Auto-increment |
| `name` | VARCHAR(200) | NOT NULL |
| `location` | VARCHAR(300) | NOT NULL |
| `mode` | VARCHAR(20) | CHECK: `'entry'` or `'recording'`; default `'entry'` |
| `created_at` | DATETIME | Server default: `now()` |

#### `pin_configs`

| Column | Type | Constraints |
|---|---|---|
| `id` | INT PK | Auto-increment |
| `lock_id` | INT | FK → locks |
| `user_id` | INT | FK → users |
| `sequence` | TEXT (NVARCHAR MAX) | JSON-serialised `list[str]` of gesture codes |
| `created_at` | DATETIME | Server default: `now()` |

**One PIN per lock** is enforced at the service layer: saving a new PIN deletes the old one in the same transaction.

#### `lock_states` (append-only audit log)

| Column | Type | Constraints |
|---|---|---|
| `id` | INT PK | Auto-increment |
| `lock_id` | INT | FK → locks |
| `state` | VARCHAR(20) | CHECK: `'locked'` or `'unlocked'` |
| `changed_by` | INT | FK → users; **nullable** — CV-triggered changes have no user session |
| `changed_at` | DATETIME | Timestamp of state change |

Rows are **never updated**. The current state is always the row with the highest `changed_at` for a given `lock_id`.
Every new lock is seeded with an initial `locked` row in the same transaction as its creation.

#### `access_log`

| Column | Type | Constraints |
|---|---|---|
| `id` | INT PK | Auto-increment |
| `lock_id` | INT | FK → locks |
| `user_id` | INT | FK → users; **nullable** |
| `timestamp` | DATETIME | UTC time of attempt |
| `result` | VARCHAR(10) | CHECK: `'success'` or `'fail'` |
| `gesture_sequence` | TEXT | JSON-serialised `list[str]` |

---

### 5.4 Service Layer

#### `lock_service.py` — Database Operations

| Function | Description |
|---|---|
| `get_all_users` / `get_user` | SELECT queries |
| `create_user` | INSERT; raises `IntegrityError` (→ HTTP 409) on duplicate username |
| `delete_user` | DELETE by id |
| `get_all_locks` / `get_lock` | SELECT queries |
| `create_lock` | INSERT lock + flush + INSERT initial `locked` state row, then commit |
| `update_lock` | Partial update — only non-`None` fields applied |
| `delete_lock` | Cascade deletes all related rows |
| `get_lock_mode` / `set_lock_mode` | Read / write the `mode` column |
| `get_lock_state` | Latest row from `lock_states` (`ORDER BY changed_at DESC LIMIT 1`) |
| `set_lock_state` | INSERT new row + broadcast `lock_state_changed` WebSocket event |
| `get_pin` / `save_pin` / `delete_pin` | PIN CRUD; `save_pin` DELETEs old PIN + INSERTs new one in one transaction |
| `get_access_log` | SELECT newest-first with LIMIT |
| `create_access_log_entry` | INSERT access log row |

#### `pin_service.py` — Gesture Verification Logic

Main entry point: `verify_gesture(db, lock_id, gesture, sequence, mode, timestamp)`

**Recording mode (`mode == "recording"`):**
1. Broadcast `pin_recording_update` WebSocket event with current gesture count and **full accumulated sequence**
2. Return `{"status": "recorded", "gesture_count": N}`
3. The PIN is **not** persisted here — the frontend calls `POST /api/locks/{id}/pin` after the user clicks "Save"

**Entry mode (`mode == "entry"`):**
1. Load `pin_config` for the lock
2. If no PIN → log `fail` + broadcast + return `{"status": "fail"}`
3. Call `_compare_sequences(incoming, stored)` (see §8)
4. On `"match"` → toggle lock state, log `success`, broadcast `gesture_event(match)` + `lock_state_changed`
5. On `"partial"` → broadcast `gesture_event(partial)`, return
6. On `"fail"` → log `fail`, broadcast `gesture_event(fail)`, return

---

### 5.5 REST API Endpoints

#### Users (`/api/users`)

| Method | Path | Status codes | Description |
|---|---|---|---|
| `GET` | `/api/users/` | 200 | List all users |
| `POST` | `/api/users/` | 201, 409 | Create user (409 on duplicate username) |
| `GET` | `/api/users/{user_id}` | 200, 404 | Get single user |
| `DELETE` | `/api/users/{user_id}` | 204, 404 | Delete user |

#### Locks (`/api/locks`)

| Method | Path | Status codes | Description |
|---|---|---|---|
| `GET` | `/api/locks/` | 200 | List all locks |
| `POST` | `/api/locks/` | 201 | Create lock (auto-seeded as `locked`) |
| `GET` | `/api/locks/{lock_id}` | 200, 404 | Get single lock |
| `PUT` | `/api/locks/{lock_id}` | 200, 404 | Partial update (name, location, mode) |
| `DELETE` | `/api/locks/{lock_id}` | 204, 404 | Delete lock + cascade |
| `GET` | `/api/locks/{lock_id}/state` | 200, 404 | Current lock state |
| `PUT` | `/api/locks/{lock_id}/state` | 200, 404 | Manual state override |
| `GET` | `/api/locks/{lock_id}/mode` | 200, 404 | Get CV mode (polled by CV module every 2 s) |
| `POST` | `/api/locks/{lock_id}/mode` | 200, 404 | Set CV mode (called by frontend) |
| `GET` | `/api/locks/{lock_id}/pin` | 200, 404 | Get PIN config (404 if none) |
| `POST` | `/api/locks/{lock_id}/pin` | 201, 404 | Save / replace PIN |
| `DELETE` | `/api/locks/{lock_id}/pin` | 204, 404 | Delete PIN |

#### Gestures & Log (`/api`)

| Method | Path | Status codes | Description |
|---|---|---|---|
| `POST` | `/api/gestures/verify` | 200, 404 | CV module gesture event (15-frame confirmed gesture) |
| `GET` | `/api/access-log?limit=N` | 200 | Recent access log entries (default 100) |

---

### 5.6 WebSocket Events

**Endpoint:** `ws://<host>/ws`
**Direction:** server → client only (frontend is receive-only)

#### `lock_state_changed`
Emitted when a lock's state changes (gesture match OR manual toggle).
```json
{
  "event": "lock_state_changed",
  "lock_id": 1,
  "state": "unlocked",
  "changed_at": "2024-01-15T10:30:00"
}
```

#### `gesture_event`
Emitted on every gesture confirmation (partial, match, or fail) during **entry mode**.
```json
{
  "event": "gesture_event",
  "lock_id": 1,
  "gesture": "FIST",
  "sequence": ["OPEN_PALM", "FIST"],
  "status": "partial"
}
```
`status` values: `"partial"` | `"match"` | `"fail"`

#### `pin_recording_update`
Emitted on every gesture confirmation during **recording mode**.
```json
{
  "event": "pin_recording_update",
  "lock_id": 1,
  "gesture": "OPEN_PALM",
  "gesture_count": 1,
  "sequence": ["OPEN_PALM"]
}
```

The backend broadcasts the **full accumulated sequence** with every recording event.
The frontend derives the current recorded sequence directly from this field — no
incremental reconstruction needed on the client side.

#### WebSocket Connection Manager (`ws_manager.py`)

Module-level singleton `manager`:
- Maintains a list of all active `WebSocket` connections
- `broadcast()` sends JSON to all connected clients; dead connections are pruned silently on the next failed send
- Auto-reconnect logic (3-second backoff) lives entirely on the **client side** in `AppContext`

---

## 6. Frontend — React Dashboard

**Location:** `frontend/`
**Stack:** React 18 · TypeScript · Vite · React Router v6

### 6.1 Routing & Page Structure

```
/              →  Dashboard     (lock grid overview)
/locks/:id     →  LockDetail    (full management for one lock)
/users         →  Users         (user CRUD)
/log           →  EventLog      (system-wide access log)
```

All routes are wrapped in `<AppProvider>` (global state + WebSocket) and `<Navbar>`.

---

### 6.2 Global State & WebSocket (AppContext)

**File:** `frontend/src/context/AppContext.tsx`

#### State Shape

```typescript
interface AppState {
  locks:             Lock[];
  lockStates:        Record<number, LockState>;
  users:             User[];
  gestureEvents:     Record<number, GestureState>;     // live per-lock gesture feed
  recordingProgress: Record<number, RecordingState>;   // live recording feed per lock
  wsConnected:       boolean;
  loading:           boolean;
  error:             string | null;
}
```

#### Actions (Reducer)

| Action type | Payload | Effect |
|---|---|---|
| `SET_LOADING` | bool | Update loading flag |
| `SET_ERROR` | string\|null | Set error banner |
| `SET_LOCKS` | Lock[] | Replace lock list |
| `SET_LOCK` | Lock | Upsert one lock |
| `REMOVE_LOCK` | number (id) | Remove from list |
| `SET_LOCK_STATE` | LockState | Update lockStates map |
| `SET_USERS` | User[] | Replace user list |
| `ADD_USER` | User | Append to user list |
| `REMOVE_USER` | number (id) | Remove from list |
| `WS_CONNECTED` | bool | Update connection indicator |
| `WS_GESTURE_EVENT` | `{lock_id, data}` | Write to gestureEvents |
| `WS_RECORDING_UPDATE` | `{lock_id, data}` | Write to recordingProgress |
| `CLEAR_RECORDING_PROGRESS` | lock_id | Clear stale recording state on mode switch |
| `SET_LOCK_MODE` | `{lock_id, mode}` | Update mode field on matching lock |

#### WebSocket Lifecycle

1. On mount → `connectWs()` opens `ws://<host>/ws` (URL built from `window.location.host` — works with both Vite proxy and nginx without hardcoding)
2. `onmessage` → parse JSON, dispatch matching action
3. `onclose` → `dispatch(WS_CONNECTED, false)` + `setTimeout(connectWs, 3000)` (auto-reconnect)
4. `onerror` → force `close()`
5. On unmount → clear reconnect timer + close WebSocket

#### Context API Surface

```typescript
interface AppContextValue {
  state:           AppState;
  refreshLocks:    () => Promise<void>;
  refreshUsers:    () => Promise<void>;
  fetchLockState:  (lockId: number) => Promise<void>;
  setLockMode:     (lockId: number, mode: 'entry' | 'recording') => Promise<void>;
  dispatch:        React.Dispatch<Action>;
}
```

`setLockMode` also dispatches `CLEAR_RECORDING_PROGRESS` when switching to `'recording'` so stale sequence data from a previous session is never shown.

---

### 6.3 Pages

#### Dashboard (`/`)

- Shows a **responsive grid of `LockCard` components** — one per lock
- Fetches all locks + their states on mount (parallel)
- **"+ Add lock" modal** — name + location form → `POST /api/locks/`
- Each card updates live via WebSocket (gesture events, state changes)
- Gesture events auto-expire after **12 seconds** of inactivity in the UI
- Recording progress auto-expires after **30 seconds** if no new event arrives

**LockCard layout:**
```
┌────────────────────────────────┐
│  [Name]          [🔒 Locked]   │
│  [Location]                    │
│                                │
│         [LockAnimation]        │
│                                │
│  [GestureIndicator]            │
│  [PinProgress]                 │
│  (or recording hint)           │
│  (or "watching for gestures…") │
│                                │
│  [🔓 Unlock] [Details] [🗑]   │
└────────────────────────────────┘
```

#### LockDetail (`/locks/:id`)

Two-column layout:

**Left column:**

| Section | Content |
|---|---|
| Status | Large `LockAnimation` + live `GestureIndicator` + `PinProgress` |
| CV Mode | "Entry mode" / "Recording mode" toggle buttons → `POST /api/locks/{id}/mode` |
| Manual Control | Unlock / Lock buttons → `PUT /api/locks/{id}/state` |

**Right column:**

| Section | Content |
|---|---|
| PIN Configuration | Current PIN as emoji chips; "Record new PIN" / "Reset PIN" buttons |
| Recording panel (when `mode === 'recording'`) | Live `PinProgress` of recorded gestures; "Save PIN" button (enabled ≥ 3 gestures); "Cancel" button; `GestureGuide` reference card |
| Access Log | Last 20 entries for this lock |

#### Users (`/users`)

- Table of all users with role badges (`admin` / `operator`)
- "Delete" button per row with confirmation dialog
- **"+ Add user" modal** — username + role radio group → `POST /api/users/`

#### EventLog (`/log`)

- Full access log (up to 500 entries) with two filters:
  - **Lock** dropdown (all locks / individual lock)
  - **Result** dropdown: All / Success / Fail
- "↻ Refresh" button

---

### 6.4 UI Components

#### `LockAnimation`
Animated SVG padlock that transitions between states:
- **`locked`** — shackle closed, red color scheme
- **`unlocked`** — shackle open (right side raised), green color scheme
- **`unknown`** — gray with `?` in keyhole

SVG path for **closed** shackle: `M16 34 C16 10 48 10 48 34`
SVG path for **open** shackle: `M16 34 C16 18 28 10 32 10 C36 10 48 18 48 34`

Size is configurable via the `size` prop (default 80 px).

#### `GestureIndicator`
Shows the currently recognized gesture with:
- Large emoji icon (from `GESTURE_EMOJI` map)
- Gesture label text
- Color-coded border/background via CSS class:
  - `partial` → yellow
  - `match` → green
  - `fail` → red
  - `recording` → blue/purple
- Optional custom sub-label (e.g. "Recording gesture 2/4")

If `gesture === null` → renders a "Waiting…" placeholder with 👋.

**Gesture emoji map (all 11 gestures):**

| Code | Emoji |
|---|---|
| `OPEN_PALM` | ✋ |
| `FIST` | ✊ |
| `INDEX_UP` | ☝️ |
| `PEACE` | ✌️ |
| `THREE` | 🤟 |
| `FOUR` | 🖖 |
| `PINKY_UP` | 🤙 |
| `OK` | 👌 |
| `ROCK` | 🤘 |
| `VULCAN` | 🖖 |
| `FINGER_GUN` | 🫵 |

#### `PinProgress`
Visual dot-based PIN progress bar:
- One dot per gesture in the sequence
- **Filled dots** show the gesture emoji
- **Empty dots** show the slot number
- Color theme follows `status` prop: `partial` / `match` / `fail` / `recording`
- Counter text: `N / total gestures`

When `total` is not provided (unknown PIN length during entry), only entered gestures are shown.

#### `GestureGuide`
Reference card showing all 11 supported gestures in a grid. Rendered inside the
recording panel so users know which gestures they can use when building a PIN.
- Gestures already used in the current recording sequence are highlighted with a `×N` usage badge

**Gesture list with descriptions:**

| Emoji | Label | Description |
|---|---|---|
| ✋ | Open Palm | All 5 fingers extended |
| ✊ | Fist | 4 main fingers curled |
| ☝️ | Index Up | Only index finger up |
| ✌️ | Peace | Index + middle up |
| 🤟 | Three | Index + middle + ring |
| 🖖 | Four | All except thumb |
| 🤙 | Pinky Up | Only pinky extended |
| 👌 | OK | Thumb + index circle |
| 🤘 | Rock | Index + pinky up |
| 🖖 | Vulcan | Four fingers, middle/ring split |
| 🫵 | Finger Gun | Thumb + index extended |

#### `Modal`
Generic centered overlay with:
- Title bar + `✕` close button
- Closes on `Escape` key and backdrop click
- Used for "Add lock" and "Add user" forms

#### `AccessLogTable`
Table rendering access log entries with:
- Timestamp, lock id, result badge (✅ success / ❌ fail)
- Gesture sequence displayed as emoji string
- Optional `lockId` prop to filter to a single lock
- Optional `maxRows` cap

#### `Navbar`
Top navigation bar with links to all four pages and a WebSocket connection indicator (`🟢` connected / `🔴` disconnected).

---

## 7. End-to-End Data Flows

### 7.1 PIN Entry Flow (gesture unlock)

```
USER shows gesture to camera
  │
  ▼
HandDetector.process_frame()
  │  21 landmarks
  ▼
GestureClassifier.classify()
  │  "FIST" (or None)
  ▼
GestureBuffer.update(gesture)
  │  stable_count++
  │  [if stable_count == 15]
  ▼
HTTP POST /api/gestures/verify
  body: {lock_id, gesture, sequence, mode:"entry", timestamp}
  │
  ▼
gestures.py router → pin_service.verify_gesture()
  │
  ├─[no PIN configured]─► log fail + broadcast gesture_event(fail) → return fail
  │
  ├─[partial match]──────► broadcast gesture_event(partial) → return partial
  │                           WebSocket → frontend updates PinProgress
  │
  ├─[full match]─────────► set_lock_state(toggle) ──► INSERT lock_states row
  │                           broadcast lock_state_changed
  │                           log success in access_log
  │                           broadcast gesture_event(match) with full sequence
  │                           return match
  │                           CV buffer: reset_sequence()
  │                           Frontend: LockAnimation transitions state
  │
  └─[fail]───────────────► log fail in access_log
                             broadcast gesture_event(fail)
                             return fail
                             CV buffer: reset_sequence()
```

### 7.2 PIN Recording Flow (setting a new PIN)

```
ADMIN clicks "Record new PIN" on LockDetail page
  │
  ▼
Frontend: setLockMode(lockId, "recording")
  POST /api/locks/{id}/mode  body: {mode:"recording"}
  dispatch SET_LOCK_MODE → UI switches to recording panel
  dispatch CLEAR_RECORDING_PROGRESS → stale sequence cleared
  │
  ▼
Backend: lock.mode = "recording" persisted in DB

CV module background poll (every 2 s):
  GET /api/locks/{id}/mode  ← returns "recording"
  buffer.set_mode("recording")  ← mode switch + reset all transient state

USER shows gestures 1…N (3–6) to camera
  │
  ▼  [each gesture: 15-frame hold → confirm → HTTP POST]
  │
  ▼
pin_service._handle_recording()
  broadcast pin_recording_update { gesture, gesture_count, sequence }
  return {status:"recorded"}
  │
  ▼
AppContext: WS_RECORDING_UPDATE → recordingProgress[lockId] updated
LockDetail: PinProgress shows accumulated gestures; GestureGuide highlights used ones

ADMIN clicks "Save PIN"  (enabled when sequence.length >= 3)
  │
  ▼
Frontend: POST /api/locks/{id}/pin  body: {user_id, sequence}
  │
  ▼
lock_service.save_pin()
  DELETE old PinConfig (if any) + INSERT new PinConfig in one transaction
  Return PinConfigResponse
  │
  ▼
Frontend: setLockMode(lockId, "entry")
  POST /api/locks/{id}/mode  body: {mode:"entry"}
  UI returns to entry mode; shows new PIN as emoji chips
```

### 7.3 Manual Lock/Unlock from Dashboard

```
ADMIN clicks "🔓 Unlock" on a LockCard or LockDetail
  │
  ▼
PUT /api/locks/{id}/state  body: {state:"unlocked"}
  │
  ▼
lock_service.set_lock_state()
  INSERT new lock_states row (naive datetime, no tzinfo)
  broadcast lock_state_changed {lock_id, state:"unlocked", changed_at}
  │
  ▼
All WebSocket clients receive event
  AppContext: SET_LOCK_STATE → lockStates[id] updated
  LockAnimation on every card for this lock transitions to "unlocked"
```

---

## 8. PIN Comparison Algorithm

**Location:** `backend/services/pin_service.py` — `_compare_sequences()`

```python
def _compare_sequences(incoming: list[str], stored: list[str]) -> str:
    if len(incoming) > len(stored):
        return "fail"
    if incoming == stored[: len(incoming)]:
        return "match" if len(incoming) == len(stored) else "partial"
    return "fail"
```

**Examples (stored = `["OPEN_PALM", "FIST", "INDEX_UP"]`):**

| Incoming sequence | Result |
|---|---|
| `["OPEN_PALM"]` | `"partial"` |
| `["OPEN_PALM", "FIST"]` | `"partial"` |
| `["OPEN_PALM", "FIST", "INDEX_UP"]` | `"match"` |
| `["OPEN_PALM", "PEACE"]` | `"fail"` (wrong gesture at position 2) |
| `["PEACE"]` | `"fail"` (wrong gesture at position 1) |
| `["OPEN_PALM", "FIST", "INDEX_UP", "PEACE"]` | `"fail"` (too long) |

The comparison is **eager** — a mismatch at any position returns `"fail"` immediately.

---

## 9. Database Schema

```
┌──────────────────┐        ┌──────────────────────┐
│      users       │        │        locks          │
│──────────────────│        │──────────────────────│
│ id  PK           │        │ id  PK               │
│ username UNIQUE  │        │ name                 │
│ role             │        │ location             │
│ created_at       │        │ mode  entry|recording│
└───────┬──────────┘        │ created_at           │
        │                   └──────┬───────────────┘
        │                          │
        │          ┌───────────────┼──────────────────────┐
        │          │               │                      │
        │  ┌───────┴────┐  ┌───────┴──────┐  ┌───────────┴──┐
        │  │ pin_configs│  │ lock_states  │  │ access_log   │
        │  │────────────│  │──────────────│  │──────────────│
        └──┤ user_id FK │  │ lock_id  FK  │  │ lock_id  FK  │
           │ lock_id FK ├──┤ state        ├  │ user_id  FK? │
           │ sequence   │  │ changed_by?  │  │ timestamp    │
           │ created_at │  │ changed_at   │  │ result       │
           └────────────┘  └──────────────┘  │ gesture_seq  │
                                              └──────────────┘
```

---

## 10. Configuration Reference

### CV Module (`.env`)

```env
BACKEND_URL=http://localhost:8000
CAMERA_INDEX=0
LOCK_ID=1
DETECTION_CONFIDENCE=0.7
TRACKING_CONFIDENCE=0.5
DEBUG_DISPLAY=false
REQUEST_TIMEOUT=2.0
MODE_POLL_INTERVAL=2.0
```

### Backend (`.env`)

```env
# SQL Server Authentication (Docker / remote)
DB_DRIVER=ODBC Driver 18 for SQL Server
DB_SERVER=mssql
DB_PORT=1433
DB_NAME=gesture_lock
DB_USER=sa
DB_PASSWORD=YourStrong@Passw0rd

# Windows Authentication (local dev with named instance)
# DB_SERVER=VIVOBOOK\MSSQLSERVER01
# DB_TRUSTED_CONNECTION=yes
# (omit DB_PORT for named instances)

# Uvicorn
BACKEND_HOST=0.0.0.0
BACKEND_PORT=8000

# CORS
CORS_ORIGIN=http://localhost:5173
```

---

## 11. Deployment — Docker Compose

**File:** `docker-compose.yml`

**Startup order:**
```
mssql
  └─► healthcheck: sqlcmd "SELECT 1" — start_period 30 s, interval 10 s, retries 10
backend
  └─► depends_on: mssql (service_healthy) + restart: on-failure
frontend
  └─► depends_on: backend
cv-module
  └─► depends_on: backend
```

| Service | Image | Exposed port |
|---|---|---|
| `mssql` | `mcr.microsoft.com/mssql/server:2022-latest` (Express) | 1433 |
| `backend` | `./backend` (Python + Uvicorn) | 8000 |
| `frontend` | `./frontend` (Vite build → nginx) | 80 |
| `cv-module` | `./cv-module` (Python) | — |

**Volumes:** `mssql_data` — persists SQL Server data files across container restarts.

**nginx (frontend):** serves the built React SPA and reverse-proxies `/api/*` and `/ws` to the backend container — the browser talks to a single origin.

> **Camera access on Windows/macOS:** Docker cannot pass a webcam through on non-Linux hosts.
> Run the CV module natively: `cd cv-module && python main.py` with `BACKEND_URL=http://localhost:8000`.
> On a Linux host, uncomment `devices: - /dev/video0:/dev/video0` in `docker-compose.yml`.

---

## 12. Non-Functional Characteristics

| Property | Value |
|---|---|
| Target camera FPS | 20 (capped; hardware may deliver more) |
| Frame budget sleep | `max(0, 50ms − frame_processing_time)` |
| Stability hold time | ~0.75 s (15 frames @ 20 FPS) |
| Post-gesture cooldown | 2 s |
| Inactivity reset | 10 s since last confirmed gesture |
| PIN length | 3 – 6 gestures (enforced by Pydantic + DB) |
| Gesture-to-backend latency | < 2.0 s (HTTP timeout) |
| WebSocket event latency | < 100 ms (local network) |
| WS reconnect backoff | 3 s |
| DB startup retries | 10 × 3 s = 30 s max |
| Consecutive frame failure limit | 30 frames before exit |
| Simultaneous locks | Unlimited (each CV instance controls one lock via `LOCK_ID`) |
| Max access log query | 500 entries (EventLog page) / 200 entries (LockDetail page) |

---

## 13. Design Decisions & Trade-offs

### Rule-based vs. ML gesture classification
The classifier uses pure geometry (landmark coordinates) with no ML model.

**Benefits:**
- Zero-latency: no model load time, no GPU required
- Deterministic and debuggable — each decision is a readable Python condition
- No training data collection or retraining required

**Limitations:**
- Requires distinct geometric profiles — gestures that only differ in orientation (THUMBS_UP/DOWN) or subtle topology (CALL_ME) were excluded
- More sensitive to extreme hand tilt and viewing angles than a trained CNN or model would be

### Append-only `lock_states` table
Lock state changes are **never updated** — only new rows are inserted.

**Benefits:**
- Full audit trail of every state change with timestamps
- Current state query is simple: `ORDER BY changed_at DESC LIMIT 1`
- Eliminates update-level race conditions
- Easy to add time-range queries for analytics without schema changes

### 15-frame stability requirement
A gesture must appear in 15 consecutive frames (~0.75 s at 20 FPS) before confirming.

**Benefits:**
- Eliminates accidental confirmations during hand transitions
- Natural "hold gesture" UX — users know they need to hold briefly
- Tunable via constant without changing any other logic

### 2-second cooldown between gestures
After each confirmation the buffer ignores input for 2 seconds.

**Benefits:**
- Prevents the same gesture from being registered twice in rapid succession
- Gives users time to transition their hand to the next gesture posture

### 10-second inactivity timeout
If no gesture is confirmed for 10 seconds, the accumulated sequence resets automatically.

**Benefits:**
- Prevents stale partial sequences from persisting between independent unlock attempts
- Users don't need an explicit "cancel" action — just walk away

### Mode stored in the `locks` table (not a separate table or cache)
The CV module polls the `mode` column via a simple GET endpoint every 2 seconds.

**Benefits:**
- Single source of truth — no cache invalidation needed
- The background poll thread keeps latency acceptable without blocking the camera loop
- The frontend can optimistically update local mode state without waiting for the CV module to confirm

### WebSocket for real-time updates (no polling)
All live events (gesture activity, lock state changes) are pushed over a persistent WebSocket with automatic 3-second reconnect.

**Benefits:**
- Sub-100 ms event delivery from gesture confirmation to dashboard update
- No polling overhead — the frontend is completely event-driven for live state
- A single `/ws` endpoint serves all event types with a discriminated `"event"` field

### Backend broadcasts the full sequence on every recording event
Each `pin_recording_update` event includes the complete `sequence` accumulated so far, not just the latest gesture.

**Benefits:**
- Frontend never needs to reconstruct the sequence incrementally
- A new browser tab loading after some gestures were already recorded gets the full state on the next event
- Eliminates off-by-one errors from incremental client-side accumulation

### No authentication on the API
The system is a university proof-of-concept. There is no JWT, session, or API key layer. Adding an auth layer (e.g., FastAPI `Security`, OAuth2 password flow) would be a straightforward next step for production deployment.

---

## 14. Developer & Evaluation Tools

**Location:** `cv-module/tools/`

Three standalone scripts support dataset collection, visual documentation, and
classifier evaluation. They are **not** part of the runtime system — they are run
manually by developers or researchers. Each script adds `cv-module/` to `sys.path`
at startup so it can import `modules.hand_detector` and `modules.gesture_classifier`
directly without installation.

```
cv-module/tools/
  collect_dataset.py   — interactive webcam dataset collector → eval_data.csv
  capture_visuals.py   — annotated screenshot tool → PNGs + montage (for report)
  evaluate.py          — metrics + plots from eval_data.csv + live benchmark
  output/              — all generated files land here (auto-created)
    gesture_<LABEL>.png
    gesture_montage.png
    confusion_matrix.png
    f1_per_class.png
    performance.png
  eval_data.csv        — collected raw samples (gitignored / generated)
```

---

### 14.1 `collect_dataset.py` — Evaluation Dataset Collector

**Purpose:** Capture ground-truth evaluation samples from a live webcam. The user
performs each of the 11 gestures on camera while holding `SPACE`; the script records
what the classifier predicts for each frame. Results are saved to a CSV for later
analysis by `evaluate.py`.

#### Usage

```bash
python cv-module/tools/collect_dataset.py [--samples 30] [--camera 0] [--output eval_data.csv]
```

| Argument | Default | Description |
|---|---|---|
| `--samples N` | `30` | Number of frames to capture per gesture while SPACE is held |
| `--camera N` | `0` | OpenCV camera index |
| `--output PATH` | `tools/eval_data.csv` | Output CSV path |
| `--countdown N` | `3` | Seconds to pause between gestures (0 to disable) |

#### Interactive Keys

| Key | Action |
|---|---|
| `SPACE` (hold) | Capture frames for the current gesture |
| `N` | Skip current gesture (no samples recorded for it) |
| `Q` | Quit early and save partial data |

#### Collection Flow

```
For each of 11 gestures (in GESTURE_ORDER):
  1. Show HUD overlay: gesture name, progress bar, "CAPTURING" indicator
  2. User holds SPACE → frames are captured
  3. Per captured frame:
       - Run HandDetector.process_frame()
       - Run GestureClassifier.classify()
       - Write row to CSV: {true_label, predicted_label, hand_detected, timestamp}
  4. Print per-gesture accuracy to console
  5. Show 3-second countdown (mirrored webcam + next-gesture label)
     All keys disabled during countdown to prevent SPACE bleed-through
  6. Move to next gesture
```

**Frame mirroring:** `cv2.flip(frame, 1)` — the frame is horizontally flipped so the
display feels like a mirror, which is natural for self-facing gesture collection.

#### CSV Output Format

```csv
true_label,predicted_label,hand_detected,timestamp
OPEN_PALM,OPEN_PALM,True,2024-01-15T10:30:00.123456
OPEN_PALM,OPEN_PALM,True,2024-01-15T10:30:00.157891
OPEN_PALM,,False,2024-01-15T10:30:00.192345
...
```

- `predicted_label` is empty string when no hand is detected
- `hand_detected` is `True`/`False`
- Only frames where the user actively held `SPACE` are recorded

#### Console Summary Table

After collection (or early quit), a summary is printed:

```
====================================================
Gesture         Samples  Correct  Accuracy
----------------------------------------------------
OK                   30       29      96.7%
OPEN_PALM            30       30     100.0%
...
----------------------------------------------------
TOTAL               330      318      96.4%
====================================================
```

---

### 14.2 `capture_visuals.py` — Annotated Screenshot Tool

**Purpose:** Produce publication-quality annotated screenshots for the academic report.
The script cycles through all 11 gestures and lets the user capture a single frame per
gesture. Each frame is annotated with the MediaPipe landmark skeleton and a HUD showing
the true label vs. detected label. Individual PNGs and a combined grid montage are saved.

#### Usage

```bash
python cv-module/tools/capture_visuals.py [--camera 0]
```

| Argument | Default | Description |
|---|---|---|
| `--camera N` | `0` | OpenCV camera index |

#### Interactive Keys

| Key | Action |
|---|---|
| `SPACE` | Capture current frame and advance to next gesture |
| `N` | Skip (a blank dark-grey cell is used in the montage) |
| `Q` | Quit early (remaining gestures get blank cells) |

#### Live Preview

While waiting for a capture, the script shows a live preview with:
- **MediaPipe skeleton** drawn on the hand in real time
- **HUD overlay** (top-left):
  - `True: <LABEL>` — white text
  - `Detected: <LABEL>` — green if correct, red if wrong, blue if no hand
- **Prompt bar** at bottom: `SPACE=capture  N=skip  Q=quit  [N/11]`

#### Capture Processing

When `SPACE` is pressed, the script:
1. Freezes the current frame
2. Re-runs MediaPipe inference in **`static_image_mode=True`** (higher accuracy,
   slower — acceptable since this is a single-shot capture, not live video)
3. Draws the **styled** landmark skeleton with `get_default_hand_landmarks_style()`
   and `get_default_hand_connections_style()`
4. Overlays the HUD with true / detected labels
5. Saves `output/gesture_<LABEL>.png`

#### Output Files

| File | Description |
|---|---|
| `output/gesture_<LABEL>.png` | Individual annotated screenshot per gesture (640×480) |
| `output/gesture_montage.png` | 4-column × 3-row grid of all 11 gestures + 1 blank cell |

**Montage layout:**
- Each cell: **320×240 px** + **24 px caption bar** at the bottom with the gesture label
- 4 × 3 = 12 cells; 11 gestures fill the first 11; last cell is dark-grey `(blank)`
- Built with `np.hstack` per row then `np.vstack` of rows

---

### 14.3 `evaluate.py` — Metrics Calculator & Performance Benchmark

**Purpose:** Read `eval_data.csv` and produce four outputs: a console classification
report, a confusion matrix heatmap, a per-class F1 bar chart, and a live camera
latency benchmark.

#### Usage

```bash
python cv-module/tools/evaluate.py [--csv eval_data.csv] [--camera 0] [--frames 200] [--skip-benchmark]
```

| Argument | Default | Description |
|---|---|---|
| `--csv PATH` | `tools/eval_data.csv` | Input CSV produced by `collect_dataset.py` |
| `--camera N` | `0` | Camera index for the live benchmark |
| `--frames N` | `200` | Number of frames to capture for the benchmark |
| `--skip-benchmark` | off | Skip the live camera section entirely |

#### Dependencies

```
pandas · matplotlib · seaborn · scikit-learn
```

#### Section A — Console Metrics

Only rows where `hand_detected == True` contribute to classification metrics
(frames without a detected hand are not the classifier's fault).

**Outputs:**
- Full `sklearn.metrics.classification_report` (precision, recall, F1, support per class)
- Overall accuracy
- Macro F1-score
- Weighted F1-score
- Hand detection rate: `detected_frames / total_frames` (includes no-hand frames)

```
==============================================================
  GESTURE CLASSIFIER - EVALUATION REPORT
==============================================================
              precision    recall  f1-score   support
          OK       1.00      0.97      0.98        30
      VULCAN       0.94      1.00      0.97        30
   OPEN_PALM       1.00      1.00      1.00        30
        ...
==============================================================
  Overall Accuracy   : 0.9727
  Macro F1-score     : 0.9712
  Weighted F1-score  : 0.9712
  Hand Detection Rate: 320/330 frames (97.0%)
==============================================================
```

#### Section B — Confusion Matrix (`output/confusion_matrix.png`)

- **Row-normalised** 11×11 heatmap — each cell shows `%` of true class predicted as each label
- Color map: `Blues`; values annotated with one decimal place
- Built with `seaborn.heatmap`; saved at 150 DPI

**Normalisation formula:**
```python
cm_norm = cm / cm.sum(axis=1, keepdims=True)  # row-wise
```
Rows with zero samples produce zero rows (no division by zero).

#### Section C — Per-Class F1 Bar Chart (`output/f1_per_class.png`)

Horizontal bar chart sorted by F1 score descending with color coding:

| Color | Threshold |
|---|---|
| 🟢 Green (`#2ecc71`) | F1 ≥ 0.90 |
| 🟡 Yellow (`#f1c40f`) | F1 ≥ 0.75 |
| 🔴 Red (`#e74c3c`) | F1 < 0.75 |

Each bar is annotated with the exact F1 value. A footnote reads:
*"Rule-based classifier — no training curves applicable"*.

#### Section D — Performance Benchmark (`output/performance.png`)

Measures the **combined latency** of `HandDetector.process_frame()` +
`GestureClassifier.classify()` over N live camera frames using
`time.perf_counter()` for nanosecond precision.

**Warm-up:** 10 frames are discarded before measurement starts to allow
MediaPipe to reach steady-state performance.

**Metrics reported:**
| Metric | Description |
|---|---|
| Mean FPS | `1000 / mean_latency_ms` |
| Mean latency | Average ms per frame |
| p95 latency | 95th-percentile ms |
| p99 latency | 99th-percentile ms |
| Min / Max | Fastest and slowest single frames |

**Plot layout (2 subplots):**
- **Top — Line chart:** latency over frame index with horizontal dashed lines for mean, p95, p99
- **Bottom — Histogram:** frame time distribution (20 bins) with the same reference lines

```
===================================
  PIPELINE PERFORMANCE BENCHMARK
===================================
  Frames measured : 200
  Mean FPS        : 42.3
  Mean latency    : 23.63 ms
  p95 latency     : 31.14 ms
  p99 latency     : 38.72 ms
  Min latency     : 18.91 ms
  Max latency     : 52.40 ms
===================================
```

#### Typical Workflow

```bash
# Step 1: collect samples (30 per gesture = 330 total)
python cv-module/tools/collect_dataset.py --samples 30

# Step 2: generate all metrics and plots
python cv-module/tools/evaluate.py

# Step 3: capture annotated screenshots for the report
python cv-module/tools/capture_visuals.py
```

All output lands in `cv-module/tools/output/` and is ready to embed in a report or paper.
