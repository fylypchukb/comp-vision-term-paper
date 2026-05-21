/**
 * api/locks.ts — all lock-related REST API calls.
 */

import { get, request } from './client';
import type { Lock, LockState, PinConfig } from '../types';

// ---------------------------------------------------------------------------
// Lock CRUD
// ---------------------------------------------------------------------------

export const getLocks = () => get<Lock[]>('/api/locks/');

export const getLock = (id: number) => get<Lock>(`/api/locks/${id}`);

export const createLock = (data: { name: string; location: string }) =>
  request<Lock>('POST', '/api/locks/', data);

export const updateLock = (id: number, data: Partial<Pick<Lock, 'name' | 'location' | 'mode'>>) =>
  request<Lock>('PUT', `/api/locks/${id}`, data);

export const deleteLock = (id: number) =>
  request<null>('DELETE', `/api/locks/${id}`);

// ---------------------------------------------------------------------------
// Lock state
// ---------------------------------------------------------------------------

export const getLockState = (id: number) =>
  get<LockState>(`/api/locks/${id}/state`);

export const setLockState = (id: number, state: 'locked' | 'unlocked', changed_by?: number) =>
  request<LockState>('PUT', `/api/locks/${id}/state`, { state, changed_by });

// ---------------------------------------------------------------------------
// Lock mode (entry / recording)
// ---------------------------------------------------------------------------

export const getLockMode = (id: number) =>
  get<{ mode: string }>(`/api/locks/${id}/mode`);

export const setLockMode = (id: number, mode: 'entry' | 'recording') =>
  request<{ mode: string }>('POST', `/api/locks/${id}/mode`, { mode });

// ---------------------------------------------------------------------------
// PIN configuration
// ---------------------------------------------------------------------------

export const getPin = (id: number) =>
  get<PinConfig>(`/api/locks/${id}/pin`);

/** Save (or replace) a PIN after a recording session. */
export const savePin = (id: number, user_id: number, sequence: string[]) =>
  request<PinConfig>('POST', `/api/locks/${id}/pin`, { user_id, sequence });

/** Admin: delete the PIN for a lock, returning it to "no PIN" state. */
export const deletePin = (id: number) =>
  request<null>('DELETE', `/api/locks/${id}/pin`);
