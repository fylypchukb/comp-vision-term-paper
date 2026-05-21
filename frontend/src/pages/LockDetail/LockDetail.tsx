/**
 * LockDetail — full management page for a single lock.
 *
 * Sections:
 *  1. Header — lock name, location, state badge
 *  2. Status panel — large animated lock + live gesture/PIN progress
 *  3. Mode switcher — entry ↔ recording
 *  4. PIN management — view/record/save/reset PIN
 *  5. Manual state override — locked / unlocked buttons
 *  6. Access log — filtered to this lock
 */

import { useEffect, useState, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useApp } from '../../context/AppContext';
import LockAnimation from '../../components/LockAnimation/LockAnimation';
import GestureIndicator from '../../components/GestureIndicator/GestureIndicator';
import PinProgress from '../../components/PinProgress/PinProgress';
import AccessLogTable from '../../components/AccessLogTable/AccessLogTable';
import * as locksApi from '../../api/locks';
import { getAccessLog } from '../../api/accessLog';
import GestureGuide from '../../components/GestureGuide/GestureGuide';
import type { PinConfig, AccessLogEntry } from '../../types';
import './LockDetail.css';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="detail-section">
      <h2 className="section-title">{title}</h2>
      {children}
    </section>
  );
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function LockDetail() {
  const { id } = useParams<{ id: string }>();
  const lockId = Number(id);
  const navigate = useNavigate();
  const { state, dispatch, setLockMode, fetchLockState } = useApp();

  const lock = state.locks.find((l) => l.id === lockId);
  const lockState = state.lockStates[lockId];
  const gesture = state.gestureEvents[lockId];
  const recording = state.recordingProgress[lockId];

  const [pin, setPin] = useState<PinConfig | null | undefined>(undefined); // undefined = not yet fetched
  const [log, setLog] = useState<AccessLogEntry[]>([]);
  const [logLoading, setLogLoading] = useState(false);
  const [pinBusy, setPinBusy] = useState(false);
  const [pinError, setPinError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  // Derive the recorded sequence directly from the WebSocket context — no
  // fragile incremental reconstruction needed.  The backend sends the full
  // accumulated sequence with every pin_recording_update event.
  const recordedSeq = lock?.mode === 'recording' ? (recording?.sequence ?? []) : [];

  // Fetch PIN config
  const fetchPin = useCallback(async () => {
    try {
      const p = await locksApi.getPin(lockId);
      setPin(p);
    } catch {
      setPin(null); // 404 = no PIN configured
    }
  }, [lockId]);

  // Fetch access log
  const fetchLog = useCallback(async () => {
    setLogLoading(true);
    try {
      const entries = await getAccessLog(200);
      setLog(entries);
    } finally {
      setLogLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!lockId) return;
    fetchPin();
    fetchLog();
    fetchLockState(lockId);
  }, [lockId, fetchPin, fetchLog, fetchLockState]);

  if (!lock) {
    return (
      <main className="detail-page">
        <button className="back-btn" onClick={() => navigate('/')}>← Back</button>
        <p className="detail-error">Lock not found.</p>
      </main>
    );
  }

  const currentState = lockState?.state ?? 'unknown';

  // ── Actions ──────────────────────────────────────────────────────────────

  const handleToggleState = async (next: 'locked' | 'unlocked') => {
    const updated = await locksApi.setLockState(lockId, next);
    if (updated) dispatch({ type: 'SET_LOCK_STATE', payload: updated });
  };

  const handleStartRecording = async () => {
    setPinError(null);
    // setLockMode clears stale recordingProgress for this lock in the context
    await setLockMode(lockId, 'recording');
  };

  const handleSavePin = async () => {
    // Capture the sequence at call time — it's derived from recording state
    const seq = recording?.sequence ?? [];
    if (seq.length < 3) {
      setPinError('PIN must have at least 3 gestures.');
      return;
    }
    const userId = state.users[0]?.id;
    if (!userId) {
      setPinError('No users found. Create a user first.');
      return;
    }
    setSaving(true);
    setPinError(null);
    try {
      const saved = await locksApi.savePin(lockId, userId, seq);
      setPin(saved);
      await setLockMode(lockId, 'entry');
    } catch (ex) {
      setPinError((ex as Error).message);
    } finally {
      setSaving(false);
    }
  };

  const handleCancelRecording = async () => {
    await setLockMode(lockId, 'entry');
  };

  const handleDeletePin = async () => {
    if (!confirm('Reset PIN for this lock? The lock will become unavailable for gesture control.')) return;
    setPinBusy(true);
    try {
      await locksApi.deletePin(lockId);
      setPin(null);
    } catch (ex) {
      setPinError((ex as Error).message);
    } finally {
      setPinBusy(false);
    }
  };

  // ── Determine what gesture/progress to render ─────────────────────────────

  const showGesture = gesture && Date.now() - gesture.ts < 12_000;
  const showRecording =
    recording && Date.now() - recording.ts < 30_000 && lock.mode === 'recording';

  const GESTURE_EMOJI: Record<string, string> = {
    OPEN_PALM: '✋', FIST: '✊', INDEX_UP: '☝️', PEACE: '✌️',
    THREE: '🤟', FOUR: '🖖', PINKY_UP: '🤙', OK: '👌',
    ROCK: '🤘', VULCAN: '🖖', FINGER_GUN: '🫵',
  };

  return (
    <main className="detail-page">
      <button className="back-btn" onClick={() => navigate('/')}>← Back</button>

      {/* ── Header ── */}
      <div className="detail-header">
        <div>
          <h1 className="detail-name">{lock.name}</h1>
          <p className="detail-location">{lock.location}</p>
        </div>
        <span className={`state-badge ${currentState}`}>
          {currentState === 'locked' ? '🔒 Locked' : currentState === 'unlocked' ? '🔓 Unlocked' : '—'}
        </span>
      </div>

      <div className="detail-grid">
        {/* ── Left column ── */}
        <div className="detail-left">

          {/* Status panel */}
          <Section title="Status">
            <div className="status-panel">
              <LockAnimation state={currentState as 'locked' | 'unlocked' | 'unknown'} size={100} />

              {showRecording ? (
                <div className="live-panel">
                  <GestureIndicator
                    gesture={recording.gesture}
                    status="recording"
                    label={`Gesture #${recording.gesture_count} recorded`}
                  />
                  <PinProgress sequence={recordedSeq} status="recording" />
                </div>
              ) : showGesture ? (
                <div className="live-panel">
                  <GestureIndicator gesture={gesture.gesture} status={gesture.status} />
                  <PinProgress
                    sequence={gesture.sequence}
                    total={pin?.sequence.length}
                    status={gesture.status}
                  />
                </div>
              ) : (
                <p className="watching-hint">
                  {lock.mode === 'recording'
                    ? '🔴 Recording mode active — show gestures'
                    : '👁 Watching for gestures…'}
                </p>
              )}
            </div>
          </Section>

          {/* Mode switcher */}
          <Section title="CV Mode">
            <div className="mode-row">
              <button
                className={`btn ${lock.mode === 'entry' ? 'btn-primary' : 'btn-ghost'}`}
                onClick={() => setLockMode(lockId, 'entry')}
                disabled={lock.mode === 'entry'}
              >
                Entry mode
              </button>
              <button
                className={`btn ${lock.mode === 'recording' ? 'btn-yellow' : 'btn-ghost'}`}
                onClick={() => setLockMode(lockId, 'recording')}
                disabled={lock.mode === 'recording'}
              >
                Recording mode
              </button>
            </div>
            <p className="mode-hint">
              {lock.mode === 'entry'
                ? 'CV module is verifying gesture PINs.'
                : 'CV module is recording a new PIN sequence.'}
            </p>
          </Section>

          {/* Manual state override */}
          <Section title="Manual Control">
            <div className="mode-row">
              <button
                className="btn btn-green"
                onClick={() => handleToggleState('unlocked')}
                disabled={currentState === 'unlocked'}
              >
                🔓 Unlock
              </button>
              <button
                className="btn btn-red"
                onClick={() => handleToggleState('locked')}
                disabled={currentState === 'locked'}
              >
                🔒 Lock
              </button>
            </div>
          </Section>
        </div>

        {/* ── Right column ── */}
        <div className="detail-right">

          {/* PIN management */}
          <Section title="PIN Configuration">
            {pin === undefined ? (
              <p className="muted">Loading…</p>
            ) : pin === null ? (
              <p className="muted">No PIN configured for this lock.</p>
            ) : (
              <div className="pin-display">
                <p className="pin-meta">
                  {pin.sequence.length} gesture PIN · configured by user #{pin.user_id}
                </p>
                <div className="pin-seq">
                  {pin.sequence.map((g, i) => (
                    <span key={i} className="pin-chip" title={g}>
                      {GESTURE_EMOJI[g] ?? g}
                    </span>
                  ))}
                </div>
              </div>
            )}

            {lock.mode === 'recording' ? (
              <div className="recording-panel">
                <p className="recording-hint">
                  🔴 Show gestures in front of the camera (3–6 total)
                </p>
                <PinProgress sequence={recordedSeq} status="recording" />
                {pinError && <p className="form-error">{pinError}</p>}
                <div className="mode-row" style={{ marginTop: '1rem' }}>
                  <button
                    className="btn btn-primary"
                    onClick={handleSavePin}
                    disabled={saving || recordedSeq.length < 3}
                  >
                    {saving ? 'Saving…' : `Save PIN (${recordedSeq.length} gesture${recordedSeq.length !== 1 ? 's' : ''})`}
                  </button>
                  <button className="btn btn-ghost" onClick={handleCancelRecording}>
                    Cancel
                  </button>
                </div>
                {/* Reference card — shows all 12 gestures; highlights those already used */}
                <GestureGuide usedGestures={recordedSeq} />
              </div>
            ) : (
              <div className="pin-actions">
                <button className="btn btn-primary" onClick={handleStartRecording}>
                  🎙 Record new PIN
                </button>
                {pin && (
                  <button
                    className="btn btn-danger"
                    onClick={handleDeletePin}
                    disabled={pinBusy}
                  >
                    {pinBusy ? 'Resetting…' : 'Reset PIN'}
                  </button>
                )}
              </div>
            )}
          </Section>

          {/* Access log */}
          <Section title="Access Log">
            {logLoading ? (
              <p className="muted">Loading…</p>
            ) : (
              <AccessLogTable entries={log} lockId={lockId} maxRows={20} />
            )}
            <button
              className="btn btn-ghost btn-sm"
              style={{ marginTop: '0.75rem' }}
              onClick={fetchLog}
            >
              Refresh
            </button>
          </Section>
        </div>
      </div>
    </main>
  );
}
