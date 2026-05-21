/**
 * Users — user management page.
 *
 * Shows a table of all users with role badges. Admins can add new users and
 * delete existing ones via inline controls and an "Add user" modal.
 */

import { useState } from 'react';
import { useApp } from '../../context/AppContext';
import Modal from '../../components/Modal/Modal';
import * as usersApi from '../../api/users';
import './Users.css';

// ---------------------------------------------------------------------------
// Add user modal
// ---------------------------------------------------------------------------

function AddUserModal({ onClose, onAdded }: { onClose: () => void; onAdded: () => void }) {
  const [username, setUsername] = useState('');
  const [role, setRole] = useState<'admin' | 'operator'>('operator');
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const { dispatch } = useApp();

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!username.trim()) return;
    setBusy(true);
    setErr(null);
    try {
      const user = await usersApi.createUser({ username: username.trim(), role });
      if (user) dispatch({ type: 'ADD_USER', payload: user });
      onAdded();
      onClose();
    } catch (ex) {
      setErr((ex as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal title="Add new user" onClose={onClose}>
      <form onSubmit={submit} className="form">
        <label className="field">
          <span className="field-label">Username</span>
          <input
            className="input"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            placeholder="e.g. alice"
            required
            autoFocus
          />
        </label>

        <fieldset className="field" style={{ border: 'none', padding: 0, margin: 0 }}>
          <legend className="field-label">Role</legend>
          <div className="radio-group">
            <label className="radio-label">
              <input
                type="radio"
                name="role"
                value="operator"
                checked={role === 'operator'}
                onChange={() => setRole('operator')}
              />
              Operator
            </label>
            <label className="radio-label">
              <input
                type="radio"
                name="role"
                value="admin"
                checked={role === 'admin'}
                onChange={() => setRole('admin')}
              />
              Admin
            </label>
          </div>
        </fieldset>

        {err && <p className="form-error">{err}</p>}

        <div className="form-actions">
          <button type="button" className="btn btn-ghost" onClick={onClose}>
            Cancel
          </button>
          <button type="submit" className="btn btn-primary" disabled={busy}>
            {busy ? 'Creating…' : 'Create user'}
          </button>
        </div>
      </form>
    </Modal>
  );
}

// ---------------------------------------------------------------------------
// Users page
// ---------------------------------------------------------------------------

function fmtDate(iso: string): string {
  return new Date(iso).toLocaleDateString(undefined, { dateStyle: 'medium' });
}

export default function Users() {
  const { state, dispatch, refreshUsers } = useApp();
  const [showAdd, setShowAdd] = useState(false);
  const [deletingId, setDeletingId] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleDelete = async (id: number, username: string) => {
    if (!confirm(`Delete user "${username}"?`)) return;
    setDeletingId(id);
    setError(null);
    try {
      await usersApi.deleteUser(id);
      dispatch({ type: 'REMOVE_USER', payload: id });
    } catch (ex) {
      setError((ex as Error).message);
    } finally {
      setDeletingId(null);
    }
  };

  return (
    <main className="users-page">
      <div className="page-header">
        <div>
          <h1 className="page-title">Users</h1>
          <p className="page-subtitle">
            {state.users.length} user{state.users.length !== 1 ? 's' : ''}
          </p>
        </div>
        <button className="btn btn-primary" onClick={() => setShowAdd(true)}>
          + Add user
        </button>
      </div>

      {error && <p className="error-banner">{error}</p>}

      {state.users.length === 0 ? (
        <div className="empty-state">
          <div className="empty-icon">👤</div>
          <p>No users yet. Add one to enable PIN configuration.</p>
          <button className="btn btn-primary" onClick={() => setShowAdd(true)}>
            Add first user
          </button>
        </div>
      ) : (
        <div className="users-table-wrapper">
          <table className="users-table">
            <thead>
              <tr>
                <th>ID</th>
                <th>Username</th>
                <th>Role</th>
                <th>Created</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {state.users.map((user) => (
                <tr key={user.id}>
                  <td className="user-id">#{user.id}</td>
                  <td className="user-name">{user.username}</td>
                  <td>
                    <span className={`role-badge ${user.role}`}>{user.role}</span>
                  </td>
                  <td className="user-date">{fmtDate(user.created_at)}</td>
                  <td className="user-actions">
                    <button
                      className="btn btn-sm btn-danger"
                      onClick={() => handleDelete(user.id, user.username)}
                      disabled={deletingId === user.id}
                    >
                      {deletingId === user.id ? '…' : 'Delete'}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {showAdd && (
        <AddUserModal
          onClose={() => setShowAdd(false)}
          onAdded={refreshUsers}
        />
      )}
    </main>
  );
}
