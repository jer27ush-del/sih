/**
 * Single place that talks to the Django API.
 * - Sends cookies (session) on every request.
 * - Adds the CSRF header on writes (token comes from the csrftoken cookie).
 * - Turns the server's {"error": {...}} bodies into ApiError objects.
 */
export class ApiError extends Error {
  status: number;
  code: string;
  fields?: Record<string, string[]>;
  constructor(status: number, code: string, message: string, fields?: Record<string, string[]>) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.code = code;
    this.fields = fields;
  }
}

const BASE = '/api';

function readCookie(name: string): string | null {
  const match = document.cookie.match(new RegExp(`(?:^|; )${name}=([^;]*)`));
  return match ? decodeURIComponent(match[1] ?? '') : null;
}

let csrfRequest: Promise<void> | null = null;

async function ensureCsrf(): Promise<void> {
  if (readCookie('csrftoken')) return;
  csrfRequest ??= fetch(`${BASE}/auth/csrf/`, { credentials: 'include' })
    .then(() => undefined)
    .finally(() => {
      csrfRequest = null;
    });
  return csrfRequest;
}

async function toApiError(response: Response): Promise<ApiError> {
  const body = await response.json().catch(() => null);
  const error = body?.error;
  if (error) {
    return new ApiError(response.status, error.code ?? 'error', error.message ?? 'Request failed.', error.fields);
  }
  if (response.status === 404) return new ApiError(404, 'not_found', 'The requested record was not found.');
  return new ApiError(response.status, 'error', 'The server could not complete the request. Please try again.');
}

interface RequestOptions {
  method?: 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE';
  body?: unknown;
  form?: FormData;
}

/** Calls the API and returns parsed JSON (or undefined for 204 responses). */
export async function api<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const method = options.method ?? 'GET';
  const headers: Record<string, string> = { Accept: 'application/json' };
  let body: BodyInit | undefined;
  if (options.form) {
    body = options.form;
  } else if (options.body !== undefined) {
    headers['Content-Type'] = 'application/json';
    body = JSON.stringify(options.body);
  }
  if (method !== 'GET') {
    await ensureCsrf();
    const token = readCookie('csrftoken');
    if (token) headers['X-CSRFToken'] = token;
  }
  const response = await fetch(`${BASE}${path}`, { method, headers, body, credentials: 'include' });
  if (response.status === 204) return undefined as T;
  if (!response.ok) throw await toApiError(response);
  return (await response.json()) as T;
}

/** Walks every page of a paginated list (capped to protect the browser). */
export async function fetchAll<T>(path: string, params: Record<string, string> = {}): Promise<T[]> {
  const rows: T[] = [];
  for (let page = 1; page <= 50; page += 1) {
    const query = new URLSearchParams({ ...params, page: String(page), page_size: '200' });
    const data = await api<{ next: string | null; results: T[] }>(`${path}?${query}`);
    rows.push(...data.results);
    if (!data.next) break;
  }
  return rows;
}

/** Downloads a file the browser cannot fetch with a plain link (the session cookie is required). */
export async function downloadFile(path: string, filename: string): Promise<void> {
  const response = await fetch(`${BASE}${path}`, { credentials: 'include' });
  if (!response.ok) throw await toApiError(response);
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

/** Readable message for any thrown value, for showing to the user. */
export function errorText(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.fields) {
      const first = Object.values(error.fields)[0];
      if (first?.[0]) return first[0];
    }
    return error.message;
  }
  return error instanceof Error ? error.message : 'Something went wrong. Please try again.';
}
