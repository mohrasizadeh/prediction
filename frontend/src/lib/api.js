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
    const err = new ApiError(res.status, e.code || "SERVER_ERROR", e.message, e.request_id);
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
