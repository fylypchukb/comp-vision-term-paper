/**
 * api/users.ts — user management REST API calls.
 */

import { get, request } from './client';
import type { User } from '../types';

export const getUsers = () => get<User[]>('/api/users/');

export const getUser = (id: number) => get<User>(`/api/users/${id}`);

export const createUser = (data: { username: string; role: 'admin' | 'operator' }) =>
  request<User>('POST', '/api/users/', data);

export const deleteUser = (id: number) =>
  request<null>('DELETE', `/api/users/${id}`);
