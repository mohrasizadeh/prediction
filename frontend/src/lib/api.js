// One way to call the API. Rules from docs/13 section 4:
// - the session lives in an HttpOnly cookie; we never store tokens in localStorage or the URL
// - every request sends credentials; writes send JSON
// - errors arrive as {error: {code, message, request_id}}
const BASE = (process.env.REACT_APP_BACKEND_URL || "").replace(/\/$/, "");

export class ApiError extends Error {
  constructor(status, code, message, requestId) {
    super(message || code);
    this.status = status;
    this.code = code;
    this.requestId = requestId;
  }
}

const listeners = new Set();
// The auth layer subscribes here to react to 401 SIGN_IN_REQUIRED and 403 ENROLL_2FA_REQUIRED anywhere.
export const onApiError = (fn) => {
  listeners.add(fn);
  return () => listeners.delete(fn);
};

// quiet: the caller handles the error itself (no global sign-in redirect).
export async function api(path, { method = "GET", body, raw, query, signal, quiet } = {}) {
  const qs = query
    ? "?" + new URLSearchParams(Object.entries(query).filter(([, v]) => v !== undefined && v !== null && v !== "")).toString()
    : "";
  const res = await fetch(`${BASE}/api${path}${qs}`, {
    method,
    signal,
    credentials: "include",
    headers: raw !== undefined ? { "Content-Type": raw.type || "application/octet-stream" } : body !== undefined ? { "Content-Type": "application/json" } : undefined,
    body: raw !== undefined ? raw : body !== undefined ? JSON.stringify(body) : undefined,
  });
  if (res.status === 204) return null;
  const data = await res.json().catch(() => null);
  if (!res.ok) {
    const e = (data && data.error) || {};
    // A body that will not parse is NOT our server reporting a fault, and calling both
    // "SERVER_ERROR" hid a real provider message behind a gateway's HTML error page: the API-Football
    // sync answered 409/502 with {"code":"PROVIDER","message":"<what they said>"}, something in front
    // of the app replaced the body, and the admin screen blamed us. Say which of the two it was and
    // keep the status, so the screen can show something an operator can act on.
    const unreadable = data === null;
    const code = e.code || (unreadable ? "UNREADABLE_ERROR" : "SERVER_ERROR");
    const message = e.message || (unreadable ? `The server answered ${res.status} and the reply could not be read.` : undefined);
    // When the body is gone the request id went with it, so fall back to the header the security
    // middleware sets on every response. It is the one thing that ties what the reader saw to a row
    // in the log, and it survives a gateway that keeps the headers and replaces the body.
    const rid = e.request_id || res.headers.get("X-Request-ID") || undefined;
    const err = new ApiError(res.status, code, message, rid);
    if (e.problems) err.problems = e.problems;
    if (!quiet) listeners.forEach((fn) => fn(err));
    throw err;
  }
  return data;
}

export const get = (path, query, opts) => api(path, { ...opts, query });
export const post = (path, body) => api(path, { method: "POST", body: body ?? {} });
export const put = (path, body) => api(path, { method: "PUT", body: body ?? {} });
export const patch = (path, body) => api(path, { method: "PATCH", body: body ?? {} });
export const del = (path, body) => api(path, { method: "DELETE", body });
// Raw file bytes (a File or Blob), e.g. an image upload.
export const putFile = (path, file) => api(path, { method: "PUT", raw: file });
// Our own image bytes (an /api/media/... address) as a Blob, e.g. to draw a share card.
export async function getBlob(image) {
  const res = await fetch(BASE + image, { credentials: "include" });
  if (!res.ok) throw new ApiError(res.status, "IMAGE_FAILED", "Could not load that image.");
  return res.blob();
}
