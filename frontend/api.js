// The only place that knows about the token, the base path, and the
// shape of a FastAPI error. Everything else calls api.get / api.post.

const TOKEN_KEY = "doclense.token";

export const token = {
  get: () => localStorage.getItem(TOKEN_KEY),
  set: (value) => localStorage.setItem(TOKEN_KEY, value),
  clear: () => localStorage.removeItem(TOKEN_KEY),
};

export class ApiError extends Error {
  constructor(status, message) {
    super(message);
    this.status = status;
  }
}

// FastAPI sends {"detail": "..."} for our errors and {"detail": [...]}
// for validation failures. Both reach the user, so both need unpacking.
function readDetail(payload, fallback) {
  const detail = payload && payload.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail) && detail.length) return detail[0].msg || fallback;
  return fallback;
}

async function request(path, { method = "GET", json, form, file } = {}) {
  const headers = {};
  const jwt = token.get();
  if (jwt) headers.Authorization = `Bearer ${jwt}`;

  let body;
  if (json !== undefined) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(json);
  } else if (form) {
    // /auth/login takes form fields, not JSON, so the /docs Authorize
    // button works. Everything else is JSON.
    body = new URLSearchParams(form);
  } else if (file) {
    // No Content-Type — the browser sets it with the multipart boundary.
    body = new FormData();
    body.append("file", file);
  }

  const response = await fetch(path, { method, headers, body });

  // A 401 while holding a token means it expired. A 401 without one is
  // a wrong password on the login page, which that page reports itself.
  if (response.status === 401 && jwt) {
    token.clear();
    location.href = "login.html";
    throw new ApiError(401, "Your session expired");
  }

  if (response.status === 204) return null;

  const payload = await response.json().catch(() => null);
  if (!response.ok) {
    throw new ApiError(response.status, readDetail(payload, "Something went wrong"));
  }
  return payload;
}

export const api = {
  get: (path) => request(path),
  post: (path, json) => request(path, { method: "POST", json }),
  form: (path, fields) => request(path, { method: "POST", form: fields }),
  upload: (path, file) => request(path, { method: "POST", file }),
  delete: (path) => request(path, { method: "DELETE" }),
};

// Send anyone without a token to the login page.
export function requireToken() {
  if (!token.get()) location.href = "login.html";
}
