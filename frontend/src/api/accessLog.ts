/**
 * api/accessLog.ts — access log REST API calls.
 */

import { get } from './client';
import type { AccessLogEntry } from '../types';

/** Fetch the most recent `limit` access log entries (default 100). */
export const getAccessLog = (limit = 100) =>
  get<AccessLogEntry[]>(`/api/access-log?limit=${limit}`);
