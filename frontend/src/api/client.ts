/** Thin fetch wrapper that understands the backend's error envelope. */

export interface ErrorEnvelope {
  error: { code: string; message: string; details?: unknown };
}

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly details: unknown;

  constructor(status: number, code: string, message: string, details?: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.details = details;
  }
}

type TokenProvider = () => string | null;
type UnauthorizedHandler = () => Promise<string | null>;

let accessTokenProvider: TokenProvider = () => null;
let unauthorizedHandler: UnauthorizedHandler | null = null;

/** Auth wires this up so every request carries the in-memory access token. */
export function setAccessTokenProvider(provider: TokenProvider): void {
  accessTokenProvider = provider;
}

/** Called once on a 401; returns a fresh access token (after a silent refresh) or null. */
export function setUnauthorizedHandler(handler: UnauthorizedHandler | null): void {
  unauthorizedHandler = handler;
}

export function getUnauthorizedHandler(): UnauthorizedHandler | null {
  return unauthorizedHandler;
}

export const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "";

/** Sent on every request; cookie-authenticated endpoints require it (CSRF defence). */
export const CLIENT_HEADER = { "X-RepoGuide-Client": "web" } as const;

function isEnvelope(body: unknown): body is ErrorEnvelope {
  return (
    typeof body === "object" &&
    body !== null &&
    "error" in body &&
    typeof (body as ErrorEnvelope).error?.code === "string"
  );
}

export async function toApiError(response: Response): Promise<ApiError> {
  let body: unknown = null;
  try {
    body = await response.json();
  } catch {
    // non-JSON error body (proxy error page, etc.)
  }
  if (isEnvelope(body)) {
    return new ApiError(response.status, body.error.code, body.error.message, body.error.details);
  }
  return new ApiError(response.status, "http_error", `Request failed (${response.status})`);
}

export function authHeaders(token: string | null = accessTokenProvider()): Record<string, string> {
  return token ? { Authorization: `Bearer ${token}` } : {};
}

export interface ApiFetchOptions extends RequestInit {
  /** Skip the refresh-and-retry dance (used by the auth endpoints themselves). */
  skipAuthRetry?: boolean;
}

async function send(path: string, init: RequestInit, token: string | null): Promise<Response> {
  const headers = new Headers(init.headers);
  headers.set("Accept", "application/json");
  if (init.body && !(init.body instanceof FormData)) {
    headers.set("Content-Type", "application/json");
  }
  for (const [key, value] of Object.entries({ ...CLIENT_HEADER, ...authHeaders(token) })) {
    headers.set(key, value);
  }
  try {
    return await fetch(`${API_BASE}${path}`, { ...init, headers, credentials: "include" });
  } catch {
    throw new ApiError(0, "network_error", "Cannot reach the RepoGuide server.");
  }
}

export async function apiFetch<T>(path: string, options: ApiFetchOptions = {}): Promise<T> {
  const { skipAuthRetry, ...init } = options;
  let response = await send(path, init, accessTokenProvider());

  if (response.status === 401 && !skipAuthRetry && unauthorizedHandler) {
    const fresh = await unauthorizedHandler();
    if (fresh) {
      response = await send(path, init, fresh);
    }
  }
  if (!response.ok) {
    throw await toApiError(response);
  }
  if (response.status === 204) {
    return undefined as T;
  }
  return (await response.json()) as T;
}
