/** The single API layer. Every network call in the app goes through here (same origin, /api). */

const TOKEN_KEY = "rm_token";

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

export function getToken(): string | null {
  try {
    return localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

export function setToken(token: string | null): void {
  try {
    if (token) localStorage.setItem(TOKEN_KEY, token);
    else localStorage.removeItem(TOKEN_KEY);
  } catch {
    /* storage unavailable: the session simply will not survive a reload */
  }
}

export const UNAUTHORIZED_EVENT = "rm:unauthorized";

async function parseError(res: Response): Promise<string> {
  try {
    const body = await res.json();
    if (typeof body?.detail === "string") return body.detail;
    if (Array.isArray(body?.detail) && body.detail[0]?.msg) return String(body.detail[0].msg);
  } catch {
    /* not JSON */
  }
  return `Request failed (${res.status})`;
}

async function raw(method: string, path: string, body?: unknown, signal?: AbortSignal): Promise<Response> {
  const headers: Record<string, string> = {};
  const token = getToken();
  if (token) headers.Authorization = `Bearer ${token}`;
  let payload: BodyInit | undefined;
  if (body instanceof FormData) payload = body;
  else if (body !== undefined) {
    headers["Content-Type"] = "application/json";
    payload = JSON.stringify(body);
  }
  let res: Response;
  try {
    res = await fetch(`/api${path}`, { method, headers, body: payload, signal });
  } catch (e) {
    if ((e as Error).name === "AbortError") throw e;
    throw new ApiError(0, "Cannot reach the ResearchMind server. Is it still running?");
  }
  if (res.status === 401 && token && !path.startsWith("/auth/")) {
    setToken(null);
    window.dispatchEvent(new Event(UNAUTHORIZED_EVENT));
  }
  if (!res.ok) throw new ApiError(res.status, await parseError(res));
  return res;
}

async function json<T>(method: string, path: string, body?: unknown, signal?: AbortSignal): Promise<T> {
  const res = await raw(method, path, body, signal);
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

export const api = {
  get: <T>(path: string, signal?: AbortSignal) => json<T>("GET", path, undefined, signal),
  post: <T>(path: string, body?: unknown) => json<T>("POST", path, body ?? {}),
  put: <T>(path: string, body?: unknown) => json<T>("PUT", path, body ?? {}),
  patch: <T>(path: string, body?: unknown) => json<T>("PATCH", path, body ?? {}),
  del: <T = void>(path: string, body?: unknown) => json<T>("DELETE", path, body),
  upload: <T>(path: string, form: FormData) => json<T>("POST", path, form),
  /** Download a protected resource (export zip, csv, markdown) and hand it to the browser as a file. */
  async download(path: string, filename: string, method: "GET" | "POST" = "GET"): Promise<void> {
    const res = await raw(method, path, method === "POST" ? {} : undefined);
    const url = URL.createObjectURL(await res.blob());
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 2000);
  },
  /** URL for opening the original PDF in a new tab (GET endpoints accept ?token= because tabs cannot send headers). */
  paperFileUrl(paperId: number, page?: number): string {
    const t = getToken();
    return `/api/papers/${paperId}/file${t ? `?token=${encodeURIComponent(t)}` : ""}${page ? `#page=${page}` : ""}`;
  },
};
