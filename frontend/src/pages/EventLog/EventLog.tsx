/**
 * EventLog — full system-wide access log with refresh and filtering.
 */

import { useEffect, useState } from 'react';
import AccessLogTable from '../../components/AccessLogTable/AccessLogTable';
import { getAccessLog } from '../../api/accessLog';
import { useApp } from '../../context/AppContext';
import type { AccessLogEntry } from '../../types';
import './EventLog.css';

export default function EventLog() {
  const { state } = useApp();
  const [entries, setEntries] = useState<AccessLogEntry[]>([]);
  const [loading, setLoading] = useState(false);
  const [filterLock, setFilterLock] = useState<number | 'all'>('all');
  const [filterResult, setFilterResult] = useState<'all' | 'success' | 'fail'>('all');

  const fetchLog = async () => {
    setLoading(true);
    try {
      const data = await getAccessLog(500);
      setEntries(data);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchLog();
  }, []);

  const filtered = entries.filter((e) => {
    if (filterLock !== 'all' && e.lock_id !== filterLock) return false;
    if (filterResult !== 'all' && e.result !== filterResult) return false;
    return true;
  });

  return (
    <main className="log-page">
      <div className="page-header">
        <div>
          <h1 className="page-title">Event Log</h1>
          <p className="page-subtitle">{filtered.length} entries</p>
        </div>
        <button className="btn btn-ghost" onClick={fetchLog} disabled={loading}>
          {loading ? 'Loading…' : '↻ Refresh'}
        </button>
      </div>

      {/* Filters */}
      <div className="log-filters">
        <label className="filter-field">
          <span className="filter-label">Lock</span>
          <select
            className="select"
            value={filterLock === 'all' ? 'all' : String(filterLock)}
            onChange={(e) =>
              setFilterLock(e.target.value === 'all' ? 'all' : Number(e.target.value))
            }
          >
            <option value="all">All locks</option>
            {state.locks.map((l) => (
              <option key={l.id} value={l.id}>
                {l.name}
              </option>
            ))}
          </select>
        </label>

        <label className="filter-field">
          <span className="filter-label">Result</span>
          <select
            className="select"
            value={filterResult}
            onChange={(e) => setFilterResult(e.target.value as 'all' | 'success' | 'fail')}
          >
            <option value="all">All results</option>
            <option value="success">Success</option>
            <option value="fail">Fail</option>
          </select>
        </label>
      </div>

      {loading && <p className="loading">Loading…</p>}

      <AccessLogTable entries={filtered} />
    </main>
  );
}
