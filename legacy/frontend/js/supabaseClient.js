/**
 * Supabase Client Initialization
 * Used by the frontend for Auth and direct DB queries (with RLS).
 */

const SUPABASE_URL = 'https://cxjeofxpfzdfqoppkosg.supabase.co';      // Replace during deploy or use env
const SUPABASE_ANON_KEY = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImN4amVvZnhwZnpkZnFvcHBrb3NnIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzM5NzQ5MjMsImV4cCI6MjA4OTU1MDkyM30.TmhKhA5FiUpZqlrt0JwTdFOOvGZIGfvx-IPKGQGx6Kw';

// Import from CDN (no build step needed for Vanilla JS)
import { createClient } from 'https://esm.sh/@supabase/supabase-js@2';

export const supabase = createClient(SUPABASE_URL, SUPABASE_ANON_KEY);
