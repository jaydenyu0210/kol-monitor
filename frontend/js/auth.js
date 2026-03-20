/**
 * Auth Module — Supabase Authentication for KOL Monitor Pro
 * Handles sign up, sign in, sign out, and session management.
 */

import { supabase } from './supabaseClient.js';

/**
 * Sign up a new user with email and password.
 */
export async function signUp(email, password) {
    const { data, error } = await supabase.auth.signUp({ email, password });
    if (error) throw error;
    return data;
}

/**
 * Sign in an existing user with email and password.
 */
export async function signIn(email, password) {
    const { data, error } = await supabase.auth.signInWithPassword({ email, password });
    if (error) throw error;
    return data;
}

/**
 * Sign out the current user and redirect to login.
 */
export async function signOut() {
    await supabase.auth.signOut();
    window.location.href = '/login.html';
}

/**
 * Get the current Supabase session (contains access_token).
 * Returns null if not authenticated.
 */
export async function getSession() {
    const { data: { session } } = await supabase.auth.getSession();
    return session;
}

/**
 * Get the current user's UUID.
 */
export async function getUserId() {
    const session = await getSession();
    return session?.user?.id || null;
}

/**
 * Redirect to login if not authenticated.
 * Call this at the top of protected pages.
 */
export async function requireAuth() {
    const session = await getSession();
    if (!session) {
        window.location.href = '/login.html';
        return null;
    }
    return session;
}
