/**
 * Dashboard — main page showing a grid of lock cards.
 *
 * Each card displays:
 *   - Lock name and location
 *   - Animated padlock (state-driven)
 *   - Current gesture + PIN progress (live via WebSocket)
 *   - Quick actions: view details, toggle state
 *
 * A modal handles adding new locks.
 */

import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useApp } from '../../context/AppContext';
import LockAnimation from '../../components/LockAnimation/LockAnimation';
import GestureIndicator from '../../components/GestureIndicator/GestureIndicator';
import PinProgress from '../../components/PinProgress/PinProgress';
import Modal from '../../components/Modal/Modal';
import * as locksApi from '../../api/locks';
import './Dashboard.css';

// ---------------------------------------------------------------------------
// Add Lock modal
// ---------------------------------------------------------------------------

function AddLockModal({ onClose, onAdded }: { onClose: () => void; onAdded: () => void }) {
  const [name, setName] = useState('');
  const [location, setLocation] = useState('');
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim() || !location.trim()) return;
    setBusy(true);
    setErr(null);
    try {
      await locksApi.createLock({ name: name.trim(), location: location.trim() });
      onAdded();
      onClose();
    } catch (ex) {
      setErr((ex as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal title="Add new lock" onClose={onClose}>
      <form onSubmit={submit} className="form">
        <label className="field">
          <span className="field-label">Lock name</span>
          <input
            className="input"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="e.g. Front Door"
            required
            autoFocus
          />
        </label>
        <label className="field">
          <span className="field-label">Location</span>
          <input
            className="input"
            value={location}
            onChange={(e) => setLocation(e.target.value)}
            placeholder="e.g. Building A, 1st floor"
            required
          />
        </label>
        {err && <p className="form-error">{err}</p>}
        <div className="form-actions">
          <button type="button" className="btn btn-ghost" onClick={onClose}>
            Cancel
          </button>
          <button type="submit" className="btn btn-primary" disabled={busy}>
            {busy ? 'Adding…' : 'Add lock'}
          </button>
        </div>
      </form>
    </Modal>
  );
}

// ---------------------------------------------------------------------------
// Single lock card
// ---------------------------------------------------------------------------

interface LockCardProps {
  lockId: number;
}

function LockCard({ lockId }: LockCardProps) {
  const { state, dispatch, refreshLocks } = useApp();
  const navigate = useNavigate();

  const lock = state.locks.find((l) => l.id === lockId);
  const lockState = state.lockStates[lockId];
  const gesture = state.gestureEvents[lockId];
  const recording = state.recordingProgress[lockId];

  const [toggling, setToggling] = useState(false);
  const [deleting, setDeleting] = useState(false);

  if (!lock) return null;

  const currentState = lockState?.state ?? 'unknown';

  const toggleState = async (e: React.MouseEvent) => {
    e.stopPropagation();
    setToggling(true);
    try {
      const next: 'locked' | 'unlocked' = currentState === 'locked' ? 'unlocked' : 'locked';
      const updated = await locksApi.setLockState(lockId, next);
      if (updated) dispatch({ type: 'SET_LOCK_STATE', payload: updated });
    } finally {
      setToggling(false);
    }
  };

  const handleDelete = async (e: React.MouseEvent) => {
    e.stopPropagation();
    if (!confirm(`Delete lock "${lock.name}"? This cannot be undone.`)) return;
    setDeleting(true);
    try {
      await locksApi.deleteLock(lockId);
      dispatch({ type: 'REMOVE_LOCK', payload: lockId });
    } finally {
      setDeleting(false);
    }
  };

  // Determine what to show in the live panel
  const showGesture =
    gesture && Date.now() - gesture.ts < 12_000; // clear after 12 s of inactivity
  const showRecording =
    recording && Date.now() - recording.ts < 30_000 && lock.mode === 'recording';

  return (
    <div
      className={`lock-card ${currentState}`}
      onClick={() => navigate(`/locks/${lockId}`)}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => e.key === 'Enter' && navigate(`/locks/${lockId}`)}
    >
      {/* Header */}
      <div className="card-header">
        <div className="card-meta">
          <span className="card-name">{lock.name}</span>
          <span className="card-location">{lock.location}</span>
        </div>
        <span className={`state-badge ${currentState}`}>
          {currentState === 'locked' ? '🔒 Locked' : currentState === 'unlocked' ? '🔓 Unlocked' : '— Unknown'}
        </span>
      </div>

      {/* Lock animation */}
      <div className="card-lock-icon">
        <LockAnimation state={currentState as 'locked' | 'unlocked' | 'unknown'} size={72} />
      </div>

      {/* Live gesture / recording panel */}
      {showRecording ? (
        <div className="card-live">
          <GestureIndicator
            gesture={recording.gesture}
            status="recording"
            label={`Recording ${recording.gesture_count} gesture(s)`}
          />
        </div>
      ) : showGesture ? (
        <div className="card-live">
          <GestureIndicator gesture={gesture.gesture} status={gesture.status} />
          <PinProgress
            sequence={gesture.sequence}
            status={gesture.status}
          />
        </div>
      ) : (
        <div className="card-live card-live--idle">
          <span className="idle-hint">
            {lock.mode === 'recording' ? '🔴 Recording mode' : '👁 Watching for gestures…'}
          </span>
        </div>
      )}

      {/* Footer actions */}
      <div className="card-footer" onClick={(e) => e.stopPropagation()}>
        <button
          className={`btn btn-sm ${currentState === 'locked' ? 'btn-green' : 'btn-red'}`}
          onClick={toggleState}
          disabled={toggling}
          title={currentState === 'locked' ? 'Unlock' : 'Lock'}
        >
          {toggling ? '…' : currentState === 'locked' ? '🔓 Unlock' : '🔒 Lock'}
        </button>
        <button
          className="btn btn-sm btn-ghost"
          onClick={() => navigate(`/locks/${lockId}`)}
        >
          Details
        </button>
        <button
          className="btn btn-sm btn-danger"
          onClick={handleDelete}
          disabled={deleting}
          title="Delete lock"
        >
          {deleting ? '…' : '🗑'}
        </button>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Dashboard page
// ---------------------------------------------------------------------------

export default function Dashboard() {
  const { state, refreshLocks } = useApp();
  const [showAdd, setShowAdd] = useState(false);

  return (
    <main className="dashboard">
      <div className="page-header">
        <div>
          <h1 className="page-title">Dashboard</h1>
          <p className="page-subtitle">
            {state.locks.length} lock{state.locks.length !== 1 ? 's' : ''} registered
          </p>
        </div>
        <button className="btn btn-primary" onClick={() => setShowAdd(true)}>
          + Add lock
        </button>
      </div>

      {state.loading && <p className="loading">Loading…</p>}
      {state.error && <p className="error-banner">{state.error}</p>}

      {state.locks.length === 0 && !state.loading ? (
        <div className="empty-state">
          <div className="empty-icon">🔐</div>
          <p>No locks configured yet.</p>
          <button className="btn btn-primary" onClick={() => setShowAdd(true)}>
            Add your first lock
          </button>
        </div>
      ) : (
        <div className="locks-grid">
          {state.locks.map((lock) => (
            <LockCard key={lock.id} lockId={lock.id} />
          ))}
        </div>
      )}

      {showAdd && (
        <AddLockModal onClose={() => setShowAdd(false)} onAdded={refreshLocks} />
      )}
    </main>
  );
}
