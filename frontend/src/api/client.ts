/**
 * api/client.ts — thin fetch wrapper used by all API modules.
 *
 * All paths are relative (e.g. "/api/locks") so they work both in development
 * (Vite proxies to localhost:8000) and production (nginx proxies to backend
 * container).
 */

const BASE = '';   // relative — works with both Vite proxy and nginx

/** Generic JSON GET. */
export async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`);
  if (!res.ok) await throwApiError(res);
  return res.json() as Promise<T>;
}

/** Generic JSON POST/PUT/DELETE with optional body. */
export async function request<T>(
  method: 'POST' | 'PUT' | 'DELETE',
  path: string,
  body?: unknown,
): Promise<T | null> {
  const res = await fetch(`${BASE}${path}`, {
    method,
    headers: body !== undefined ? { 'Content-Type': 'application/json' } : {},
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) await throwApiError(res);
  // 204 No Content → no body
  if (res.status === 204) return null;
  return res.json() as Promise<T>;
}

/** Extract a readable error message from an API error response. */
async function throwApiError(res: Response): Promise<never> {
  let detail = `HTTP ${res.status}`;
  try {
    const data = (await res.json()) as { detail?: string };
    if (data.detail) detail = data.detail;
  } catch {
    // ignore JSON parse error
  }
  throw new Error(detail);
}
