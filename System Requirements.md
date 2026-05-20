# Gesture Smart Lock — System Requirements

## 1. System Description

An automatic smart lock control system based on hand gesture recognition. The CV module captures a video stream from a camera, recognizes gestures via MediaPipe Hands, and sends events to the server. The user configures a PIN sequence of gestures through the web interface. To open/close the lock, the user must show the correct gesture sequence. All events are logged in the database, and the lock state is updated on the dashboard in real time via WebSocket.

---

## 2. Functional Requirements

### CV Module

- Capture video stream from camera in real time
- Detect hand and 21 landmark points via MediaPipe Hands
- Classify 12 gestures using a rule-based method (geometric analysis of landmark coordinates)
- Gesture hold buffer — gesture is confirmed after 15 consecutive stable frames
- 2-second cooldown after each recognized gesture
- Verify entered PIN sequence (send to server after each gesture)
- Send events to server via HTTP POST

### Server

- REST API for managing locks, users, PIN configurations, and lock states
- WebSocket `/ws` — real-time event push to frontend
- Verify PIN sequence against the one stored in the database
- Change lock state after successful PIN verification
- Log every access attempt in `access_log`
- Asynchronous database operations

### Frontend

- Dashboard with a list of all locks
- Lock animation (locked/unlocked states)
- Real-time updates via WebSocket
- Display current recognized gesture + PIN entry progress
- Event log with timestamps
- UI for configuring PIN sequence per lock
- UI for adding locks and users

---

## 3. Non-Functional Requirements

- Camera FPS: minimum 20 frames/sec
- Latency from gesture to UI update: up to 500 ms
- Code must comply with PEP 8 standard
- `requirements.txt` required for each service
- Key code blocks must be commented
- Deployment via Docker Compose with a single command

---

## 4. Architecture

Three independent services deployed via Docker Compose:

**CV Module** → HTTP POST → **Backend (FastAPI)** → PostgreSQL

**Backend (FastAPI)** → WebSocket → **Frontend (React)**

- CV module and backend are separate containers (CV requires camera access)
- CV ↔ Backend communication via internal Docker network
- Frontend connects to Backend via WebSocket for real-time events
- Frontend communicates with Backend via REST API for data management

---

## 5. Database (SQL Server)

### `users`

id, username, role (admin/operator), created_at

### `locks`

id, name, location, created_at

### `pin_configs`

id, lock_id, user_id, sequence (JSON string), created_at

### `lock_states`

id, lock_id, state (locked/unlocked), changed_by (user_id), changed_at

### `access_log`

id, lock_id, user_id, timestamp, result (success/fail), gesture_sequence (JSON string)

---

## 6. Gestures (12 total)

| Code | Gesture | Description |
| --- | --- | --- |
| `OPEN_PALM` | ✋ | All 5 fingers extended |
| `FIST` | ✊ | All 5 fingers curled |
| `INDEX_UP` | ☝️ | Only index finger extended |
| `PEACE` | ✌️ | Index + middle extended |
| `THREE` | 🤟 | Index + middle + ring extended |
| `FOUR` | 🖖 | All except thumb extended |
| `THUMBS_UP` | 👍 | Thumb pointing up |
| `THUMBS_DOWN` | 👎 | Thumb pointing down |
| `PINKY_UP` | 🤙 | Only pinky extended |
| `OK` | 👌 | Thumb + index form a circle |
| `ROCK` | 🤘 | Index + pinky extended |
| `CALL_ME` | 🤙 | Thumb + pinky extended |

---

## 7. Project Structure

```
gesture-lock/
├── cv-module/
│   ├── main.py
│   ├── hand_detector.py
│   ├── gesture_classifier.py
│   ├── gesture_buffer.py
│   └── requirements.txt
├── backend/
│   ├── main.py
│   ├── routers/
│   │   ├── locks.py
│   │   ├── users.py
│   │   └── gestures.py
│   ├── services/
│   │   ├── lock_service.py
│   │   └── pin_service.py
│   ├── models/
│   ├── schemas/
│   ├── database.py
│   └── requirements.txt
├── frontend/
│   └── (Vite + React + TypeScript)
└── docker-compose.yml
```

---

## 8. Technology Stack

| Component | Technology |
| --- | --- |
| Hand detection | MediaPipe Hands |
| Video processing | OpenCV |
| Matrix operations | NumPy |
| Server API | FastAPI + Uvicorn |
| Data validation | Pydantic |
| ORM | SQLAlchemy Async + aioodbc |
| Database | SQL Server 2022 |
| WebSocket | FastAPI WebSocket |
| Containerization | Docker + Docker Compose |
| Frontend | React 18 + TypeScript + Vite |

---

## 9. PIN Logic

### PIN Structure

- Minimum length: 3 gestures
- Maximum length: 6 gestures
- The same gesture can repeat within the sequence

### Entry Algorithm

1. User starts entering PIN — system switches to waiting mode
2. Each confirmed gesture (15-frame hold) is added to the current sequence buffer
3. 2-second cooldown between gestures to prevent doubling
4. After each added gesture — HTTP POST to server with current progress
5. Server compares current buffer against the beginning of the stored PIN
6. If buffer matches the full PIN → command is executed
7. If buffer does not match at any step → reset, start from scratch
8. Timeout between gestures — 10 seconds. If no gesture shown → buffer resets

### PIN Configuration via UI

- User selects a lock
- Clicks "Record new PIN"
- Shows gestures in front of the camera one by one
- UI shows progress in real time via WebSocket
- After the last gesture, clicks "Save"
- Server stores the sequence in `pin_configs`

### PIN Reset

- Admin can reset PIN for any lock via UI
- Old PIN is deleted from `pin_configs`, lock enters "no PIN" state — unavailable for gesture control

---

## 10. Gesture Classifier — Geometric Logic

### Landmark Indices

```
Thumb:     CMC=1, MCP=2,  IP=3,  TIP=4
Index:     MCP=5, PIP=6,  DIP=7, TIP=8
Middle:    MCP=9, PIP=10, DIP=11, TIP=12
Ring:      MCP=13, PIP=14, DIP=15, TIP=16
Pinky:     MCP=17, PIP=18, DIP=19, TIP=20
Wrist:     0
```

### Finger State Detection

**Index, Middle, Ring, Pinky:**

- Extended → `TIP.y < PIP.y`
- Curled → `TIP.y > PIP.y`

**Thumb (moves along X axis):**

- Extended → `TIP.x < IP.x` (for right hand)
- Curled → `TIP.x > IP.x`

**Hand orientation:**

- Pointing up → `MCP of middle (9).y < wrist (0).y`
- Used to distinguish `THUMBS_UP` vs `THUMBS_DOWN`

### Per-Gesture Logic

| Gesture | Condition |
| --- | --- |
| `OPEN_PALM` | All 5 fingers extended |
| `FIST` | All 5 fingers curled |
| `INDEX_UP` | Index extended; Middle, Ring, Pinky, Thumb curled |
| `PEACE` | Index + Middle extended; Ring, Pinky, Thumb curled |
| `THREE` | Index + Middle + Ring extended; Pinky, Thumb curled |
| `FOUR` | Index + Middle + Ring + Pinky extended; Thumb curled |
| `THUMBS_UP` | Thumb extended; others curled; hand pointing up |
| `THUMBS_DOWN` | Thumb extended; others curled; `TIP.y > MCP.y` |
| `PINKY_UP` | Pinky extended; Index, Middle, Ring, Thumb curled |
| `ROCK` | Index + Pinky extended; Middle, Ring, Thumb curled |
| `CALL_ME` | Thumb + Pinky extended; Index, Middle, Ring curled |
| `OK` | Distance between Index TIP (8) and Thumb TIP (4) < 0.05 (normalized); Middle + Ring + Pinky extended |