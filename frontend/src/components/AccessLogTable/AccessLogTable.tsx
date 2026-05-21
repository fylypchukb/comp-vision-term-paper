/**
 * AccessLogTable — renders access log entries in a table.
 * Supports optional lock-level filtering (when lockId is given, only that
 * lock's entries are shown).
 */

import type { AccessLogEntry } from '../../types';
import './AccessLogTable.css';

const GESTURE_EMOJI: Record<string, string> = {
  OPEN_PALM: '✋', FIST: '✊', INDEX_UP: '☝️', PEACE: '✌️',
  THREE: '🤟', FOUR: '🖖', PINKY_UP: '🤙', OK: '👌',
  ROCK: '🤘', VULCAN: '🖖', FINGER_GUN: '🫵',
};

function fmtDate(iso: string): string {
  return new Date(iso).toLocaleString(undefined, {
    dateStyle: 'short',
    timeStyle: 'medium',
  });
}

interface Props {
  entries: AccessLogEntry[];
  lockId?: number;
  maxRows?: number;
}

export default function AccessLogTable({ entries, lockId, maxRows }: Props) {
  const rows = entries
    .filter((e) => lockId === undefined || e.lock_id === lockId)
    .slice(0, maxRows);

  if (rows.length === 0) {
    return <p className="log-empty">No access events recorded yet.</p>;
  }

  return (
    <div className="log-table-wrapper">
      <table className="log-table">
        <thead>
          <tr>
            <th>Time</th>
            {lockId === undefined && <th>Lock</th>}
            <th>Result</th>
            <th>Sequence</th>
            <th>User</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((e) => (
            <tr key={e.id} className={`log-row ${e.result}`}>
              <td className="log-time">{fmtDate(e.timestamp)}</td>
              {lockId === undefined && <td>#{e.lock_id}</td>}
              <td>
                <span className={`log-badge ${e.result}`}>
                  {e.result === 'success' ? '✅ OK' : '❌ Fail'}
                </span>
              </td>
              <td className="log-seq">
                {e.gesture_sequence.map((g, i) => (
                  <span key={i} className="seq-item" title={g}>
                    {GESTURE_EMOJI[g] ?? g}
                  </span>
                ))}
              </td>
              <td className="log-user">
                {e.user_id != null ? `#${e.user_id}` : '—'}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
