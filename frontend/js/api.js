/**
 * API Fetch Wrapper — Automatically injects Supabase JWT
 * into every request sent to the Railway backend.
 */

import { getSession } from './auth.js';

// Railway backend URL — replace with your deployed URL
const RAILWAY_API = 'http://localhost:3001';

/**
 * Authenticated fetch wrapper.
 * Automatically attaches the Supabase access_token as a Bearer token.
 * Redirects to login on 401 responses.
 *
 * Usage:
 *   const data = await apiFetch('/api/kols');
 *   const res  = await apiFetch('/api/kols', { method: 'POST', body: JSON.stringify({...}) });
 */
export async function apiFetch(path, options = {}) {
    const session = await getSession();
    if (!session) {
        window.location.href = '/login.html';
        return null;
    }

    const headers = {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${session.access_token}`,
        ...(options.headers || {}),
    };

    const res = await fetch(`${RAILWAY_API}${path}`, {
        ...options,
        headers,
    });

    if (res.status === 401) {
        // Token expired or invalid — force re-login
        window.location.href = '/login.html';
        return null;
    }

    if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: 'Unknown error' }));
        throw new Error(err.detail || `API error: ${res.status}`);
    }

    return res.json();
}

/**
 * Shorthand for GET requests.
 */
export async function apiGet(path) {
    return apiFetch(path);
}

/**
 * Shorthand for POST requests.
 */
export async function apiPost(path, body) {
    return apiFetch(path, {
        method: 'POST',
        body: JSON.stringify(body),
    });
}

/**
 * Shorthand for PUT requests.
 */
export async function apiPut(path, body) {
    return apiFetch(path, {
        method: 'PUT',
        body: JSON.stringify(body),
    });
}

/**
 * Shorthand for DELETE requests.
 */
export async function apiDelete(path) {
    return apiFetch(path, { method: 'DELETE' });
}
