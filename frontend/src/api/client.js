const BASE = `${import.meta.env.VITE_API_URL || ''}/api`;

function getCsrfToken() {
  const m = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
  return m ? decodeURIComponent(m[1]) : '';
}

async function request(path, options = {}) {
  const url = `${BASE}${path}`;
  const method = (options.method || 'GET').toUpperCase();
  const csrfHeaders = ['POST', 'PUT', 'PATCH', 'DELETE'].includes(method)
    ? { 'X-CSRFToken': getCsrfToken() }
    : {};
  const config = {
    credentials: 'include',
    headers: { 'Content-Type': 'application/json', ...csrfHeaders, ...options.headers },
    ...options,
  };
  if (config.body && typeof config.body === 'object' && !(config.body instanceof FormData)) {
    config.body = JSON.stringify(config.body);
  }
  if (config.body instanceof FormData) {
    delete config.headers['Content-Type'];
  }
  const res = await fetch(url, config);
  if (!res.ok) {
    const err = await res.json().catch(() => ({ error: res.statusText }));
    throw new Error(err.error || err.detail || JSON.stringify(err));
  }
  if (res.status === 204) return null;
  return res.json();
}

export const api = {
  get: (path) => request(path),
  post: (path, body) => request(path, { method: 'POST', body }),
  patch: (path, body) => request(path, { method: 'PATCH', body }),
  delete: (path) => request(path, { method: 'DELETE' }),
  upload: (path, formData) => request(path, { method: 'POST', body: formData }),
};
