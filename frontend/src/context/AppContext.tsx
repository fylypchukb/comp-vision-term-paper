/**
 * context/AppContext.tsx — global application state + WebSocket integration.
 *
 * Provides:
 *   - locks[], lockStates{}, users[] fetched from REST API
 *   - gestureEvents{} and recordingProgress{} populated by WebSocket messages
 *   - wsConnected flag
 *   - Actions: refreshLocks, refreshUsers, updateLockState, setMode, etc.
 *
 * WebSocket reconnects automatically with a 3-second backoff when the
 * connection drops.
 */

import React, {
  createContext,
  useContext,
  useEffect,
  useReducer,
  useRef,
  useCallback,
} from 'react';
import type {
  Lock,
  LockState,
  User,
  GestureState,
  RecordingState,
  WsEvent,
} from '../types';
import * as locksApi from '../api/locks';
import * as usersApi from '../api/users';

// ---------------------------------------------------------------------------
// State shape
// ---------------------------------------------------------------------------

interface AppState {
  locks: Lock[];
  lockStates: Record<number, LockState>;
  users: User[];
  gestureEvents: Record<number, GestureState>;
  recordingProgress: Record<number, RecordingState>;
  wsConnected: boolean;
  loading: boolean;
  error: string | null;
}

const initialState: AppState = {
  locks: [],
  lockStates: {},
  users: [],
  gestureEvents: {},
  recordingProgress: {},
  wsConnected: false,
  loading: false,
  error: null,
};

// ---------------------------------------------------------------------------
// Actions
// ---------------------------------------------------------------------------

type Action =
  | { type: 'SET_LOADING'; payload: boolean }
  | { type: 'SET_ERROR'; payload: string | null }
  | { type: 'SET_LOCKS'; payload: Lock[] }
  | { type: 'SET_LOCK'; payload: Lock }
  | { type: 'REMOVE_LOCK'; payload: number }
  | { type: 'SET_LOCK_STATE'; payload: LockState }
  | { type: 'SET_USERS'; payload: User[] }
  | { type: 'ADD_USER'; payload: User }
  | { type: 'REMOVE_USER'; payload: number }
  | { type: 'WS_CONNECTED'; payload: boolean }
  | { type: 'WS_GESTURE_EVENT'; payload: { lock_id: number; data: GestureState } }
  | { type: 'WS_RECORDING_UPDATE'; payload: { lock_id: number; data: RecordingState } }
  | { type: 'CLEAR_RECORDING_PROGRESS'; payload: number /* lock_id */ }
  | { type: 'SET_LOCK_MODE'; payload: { lock_id: number; mode: 'entry' | 'recording' } };

function reducer(state: AppState, action: Action): AppState {
  switch (action.type) {
    case 'SET_LOADING':
      return { ...state, loading: action.payload };
    case 'SET_ERROR':
      return { ...state, error: action.payload };
    case 'SET_LOCKS':
      return { ...state, locks: action.payload };
    case 'SET_LOCK':
      return {
        ...state,
        locks: state.locks.some((l) => l.id === action.payload.id)
          ? state.locks.map((l) => (l.id === action.payload.id ? action.payload : l))
          : [...state.locks, action.payload],
      };
    case 'REMOVE_LOCK':
      return {
        ...state,
        locks: state.locks.filter((l) => l.id !== action.payload),
      };
    case 'SET_LOCK_STATE':
      return {
        ...state,
        lockStates: { ...state.lockStates, [action.payload.lock_id]: action.payload },
      };
    case 'SET_USERS':
      return { ...state, users: action.payload };
    case 'ADD_USER':
      return { ...state, users: [...state.users, action.payload] };
    case 'REMOVE_USER':
      return { ...state, users: state.users.filter((u) => u.id !== action.payload) };
    case 'WS_CONNECTED':
      return { ...state, wsConnected: action.payload };
    case 'WS_GESTURE_EVENT':
      return {
        ...state,
        gestureEvents: {
          ...state.gestureEvents,
          [action.payload.lock_id]: action.payload.data,
        },
      };
    case 'WS_RECORDING_UPDATE':
      return {
        ...state,
        recordingProgress: {
          ...state.recordingProgress,
          [action.payload.lock_id]: action.payload.data,
        },
      };
    case 'CLEAR_RECORDING_PROGRESS': {
      // eslint-disable-next-line @typescript-eslint/no-unused-vars
      const { [action.payload]: _removed, ...rest } = state.recordingProgress;
      return { ...state, recordingProgress: rest };
    }
    case 'SET_LOCK_MODE':
      return {
        ...state,
        locks: state.locks.map((l) =>
          l.id === action.payload.lock_id ? { ...l, mode: action.payload.mode } : l,
        ),
      };
    default:
      return state;
  }
}

// ---------------------------------------------------------------------------
// Context interface
// ---------------------------------------------------------------------------

interface AppContextValue {
  state: AppState;
  refreshLocks: () => Promise<void>;
  refreshUsers: () => Promise<void>;
  fetchLockState: (lockId: number) => Promise<void>;
  setLockMode: (lockId: number, mode: 'entry' | 'recording') => Promise<void>;
  dispatch: React.Dispatch<Action>;
}

const AppContext = createContext<AppContextValue | null>(null);

// ---------------------------------------------------------------------------
// Provider
// ---------------------------------------------------------------------------

/** Build the WebSocket URL, working with both the Vite proxy and nginx. */
function buildWsUrl(): string {
  const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  return `${proto}//${window.location.host}/ws`;
}

export function AppProvider({ children }: { children: React.ReactNode }) {
  const [state, dispatch] = useReducer(reducer, initialState);
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  // -------------------------------------------------------------------------
  // REST API helpers
  // -------------------------------------------------------------------------

  const refreshLocks = useCallback(async () => {
    try {
      const locks = await locksApi.getLocks();
      dispatch({ type: 'SET_LOCKS', payload: locks });

      // Fetch state for each lock in parallel (best-effort)
      await Promise.all(
        locks.map(async (lock) => {
          try {
            const st = await locksApi.getLockState(lock.id);
            dispatch({ type: 'SET_LOCK_STATE', payload: st });
          } catch {
            // Lock may not have a state yet — ignore
          }
        }),
      );
    } catch (err) {
      dispatch({ type: 'SET_ERROR', payload: (err as Error).message });
    }
  }, []);

  const refreshUsers = useCallback(async () => {
    try {
      const users = await usersApi.getUsers();
      dispatch({ type: 'SET_USERS', payload: users });
    } catch (err) {
      dispatch({ type: 'SET_ERROR', payload: (err as Error).message });
    }
  }, []);

  const fetchLockState = useCallback(async (lockId: number) => {
    try {
      const st = await locksApi.getLockState(lockId);
      dispatch({ type: 'SET_LOCK_STATE', payload: st });
    } catch {
      // no state yet
    }
  }, []);

  const setLockMode = useCallback(
    async (lockId: number, mode: 'entry' | 'recording') => {
      await locksApi.setLockMode(lockId, mode);
      dispatch({ type: 'SET_LOCK_MODE', payload: { lock_id: lockId, mode } });
      // Clear any stale recording progress from a previous session so the UI
      // starts fresh and doesn't show gestures from an older recording run.
      if (mode === 'recording') {
        dispatch({ type: 'CLEAR_RECORDING_PROGRESS', payload: lockId });
      }
    },
    [],
  );

  // -------------------------------------------------------------------------
  // WebSocket management
  // -------------------------------------------------------------------------

  const connectWs = useCallback(() => {
    if (wsRef.current && wsRef.current.readyState < WebSocket.CLOSING) return;

    const ws = new WebSocket(buildWsUrl());
    wsRef.current = ws;

    ws.onopen = () => {
      dispatch({ type: 'WS_CONNECTED', payload: true });
    };

    ws.onmessage = (evt) => {
      try {
        const msg = JSON.parse(evt.data as string) as WsEvent;
        switch (msg.event) {
          case 'lock_state_changed':
            // Refresh full state record from API to get the complete object
            dispatch({
              type: 'SET_LOCK_STATE',
              payload: {
                id: 0, // placeholder; overwritten on next full fetch
                lock_id: msg.lock_id,
                state: msg.state,
                changed_by: null,
                changed_at: msg.changed_at,
              },
            });
            break;

          case 'gesture_event':
            dispatch({
              type: 'WS_GESTURE_EVENT',
              payload: {
                lock_id: msg.lock_id,
                data: {
                  gesture: msg.gesture,
                  sequence: msg.sequence,
                  status: msg.status,
                  ts: Date.now(),
                },
              },
            });
            break;

          case 'pin_recording_update':
            dispatch({
              type: 'WS_RECORDING_UPDATE',
              payload: {
                lock_id: msg.lock_id,
                data: {
                  gesture: msg.gesture,
                  gesture_count: msg.gesture_count,
                  sequence: msg.sequence, // full accumulated sequence from backend
                  ts: Date.now(),
                },
              },
            });
            break;
        }
      } catch {
        // Malformed message — ignore
      }
    };

    ws.onclose = () => {
      dispatch({ type: 'WS_CONNECTED', payload: false });
      // Reconnect after 3 seconds
      reconnectTimer.current = setTimeout(connectWs, 3000);
    };

    ws.onerror = () => {
      ws.close();
    };
  }, []);

  // -------------------------------------------------------------------------
  // Initial data load + WebSocket connect
  // -------------------------------------------------------------------------

  useEffect(() => {
    dispatch({ type: 'SET_LOADING', payload: true });
    Promise.all([refreshLocks(), refreshUsers()]).finally(() => {
      dispatch({ type: 'SET_LOADING', payload: false });
    });
    connectWs();

    return () => {
      if (reconnectTimer.current) clearTimeout(reconnectTimer.current);
      wsRef.current?.close();
    };
  }, [refreshLocks, refreshUsers, connectWs]);

  return (
    <AppContext.Provider
      value={{ state, refreshLocks, refreshUsers, fetchLockState, setLockMode, dispatch }}
    >
      {children}
    </AppContext.Provider>
  );
}

// ---------------------------------------------------------------------------
// Hook
// ---------------------------------------------------------------------------

export function useApp(): AppContextValue {
  const ctx = useContext(AppContext);
  if (!ctx) throw new Error('useApp must be used inside AppProvider');
  return ctx;
}
