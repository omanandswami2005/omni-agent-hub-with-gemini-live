/**
 * REST API client for backend HTTP endpoints.
 * Auto-attaches Firebase auth token, handles 401 refresh + retry and 429 rate limits.
 */

import { useAuthStore } from '@/stores/authStore';
import { auth } from '@/lib/firebase';

const BASE_URL = (import.meta.env.VITE_API_URL || '') + '/api/v1';

async function request(path, options = {}) {
    const { token: explicitToken, ...fetchOptions } = options;
    const token = explicitToken || useAuthStore.getState().token;
    const isFormData = fetchOptions.body instanceof FormData;
    const headers = {
        ...(!isFormData && { 'Content-Type': 'application/json' }),
        ...(token && { Authorization: `Bearer ${token}` }),
        ...options.headers,
    };
    // Remove undefined header values (e.g. explicit Content-Type: undefined)
    Object.keys(headers).forEach(k => { if (headers[k] === undefined) delete headers[k]; });

    let res = await fetch(`${BASE_URL}${path}`, { ...fetchOptions, headers });

    // 401 — try refreshing the token once and retry
    if (res.status === 401 && auth.currentUser) {
        const freshToken = await auth.currentUser.getIdToken(true);
        useAuthStore.getState().setUser(auth.currentUser, freshToken);
        headers.Authorization = `Bearer ${freshToken}`;
        res = await fetch(`${BASE_URL}${path}`, { ...fetchOptions, headers });
    }

    if (res.status === 429) {
        throw new Error('Rate limited — please slow down and try again.');
    }

    if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        const err = new Error(body.detail || `API error ${res.status}`);
        err.status = res.status;
        throw err;
    }

    if (res.status === 204) return null;
    return res.json();
}

export const api = {
    get: (path, opts) => request(path, { method: 'GET', ...opts }),
    post: (path, data, opts) => request(path, { method: 'POST', body: JSON.stringify(data), ...opts }),
    put: (path, data, opts) => request(path, { method: 'PUT', body: JSON.stringify(data), ...opts }),
    delete: (path, opts) => request(path, { method: 'DELETE', ...opts }),
    /** POST with FormData body (multipart) */
    postForm: (path, formData, opts) => request(path, { method: 'POST', body: formData, ...opts }),
};
