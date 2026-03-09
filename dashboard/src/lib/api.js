/**
 * REST API client for backend HTTP endpoints.
 */

const BASE_URL = import.meta.env.VITE_API_URL || '/api';

async function request(path, options = {}) {
    const { token, ...fetchOptions } = options;
    const headers = {
        'Content-Type': 'application/json',
        ...(token && { Authorization: `Bearer ${token}` }),
        ...options.headers,
    };

    const res = await fetch(`${BASE_URL}${path}`, { ...fetchOptions, headers });
    if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.detail || `API error ${res.status}`);
    }
    return res.json();
}

export const api = {
    get: (path, opts) => request(path, { method: 'GET', ...opts }),
    post: (path, data, opts) => request(path, { method: 'POST', body: JSON.stringify(data), ...opts }),
    put: (path, data, opts) => request(path, { method: 'PUT', body: JSON.stringify(data), ...opts }),
    delete: (path, opts) => request(path, { method: 'DELETE', ...opts }),
};
