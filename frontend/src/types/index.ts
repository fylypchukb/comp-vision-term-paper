/**
 * types/index.ts — shared TypeScript interfaces for API responses and
 * WebSocket events mirroring the backend Pydantic schemas.
 */

// ---------------------------------------------------------------------------
// REST API response shapes
// ---------------------------------------------------------------------------

export interface User {
  id: number;
  username: string;
  role: 'admin' | 'operator';
  created_at: string;
}

export interface Lock {
  id: number;
  name: string;
  location: string;
  mode: 'entry' | 'recording';
  created_at: string;
}

export interface LockState {
  id: number;
  lock_id: number;
  state: 'locked' | 'unlocked';
  changed_by: number | null;
  changed_at: string;
}

export interface PinConfig {
  id: number;
  lock_id: number;
  user_id: number;
  sequence: string[];
  created_at: string;
}

export interface AccessLogEntry {
  id: number;
  lock_id: number;
  user_id: number | null;
  timestamp: string;
  result: 'success' | 'fail';
  gesture_sequence: string[];
}

// ---------------------------------------------------------------------------
// WebSocket event shapes (matches backend ws_manager broadcasts)
// ---------------------------------------------------------------------------

export interface WsLockStateChanged {
  event: 'lock_state_changed';
  lock_id: number;
  state: 'locked' | 'unlocked';
  changed_at: string;
}

export interface WsGestureEvent {
  event: 'gesture_event';
  lock_id: number;
  gesture: string;
  sequence: string[];
  status: 'partial' | 'match' | 'fail';
}

export interface WsPinRecordingUpdate {
  event: 'pin_recording_update';
  lock_id: number;
  gesture: string;
  gesture_count: number;
  sequence: string[]; // full accumulated sequence sent by the backend
}

export type WsEvent = WsLockStateChanged | WsGestureEvent | WsPinRecordingUpdate;

// ---------------------------------------------------------------------------
// UI-level helper types
// ---------------------------------------------------------------------------

/** Per-lock gesture tracking kept in AppContext. */
export interface GestureState {
  gesture: string;
  sequence: string[];
  status: 'partial' | 'match' | 'fail';
  ts: number; // Date.now() of last update — used to auto-clear stale data
}

/** Per-lock PIN recording progress kept in AppContext. */
export interface RecordingState {
  gesture: string;       // the last gesture received
  gesture_count: number; // total gestures recorded so far
  sequence: string[];    // full accumulated sequence (authoritative source of truth)
  ts: number;            // Date.now() of last update
}
