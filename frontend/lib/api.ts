import { createClient } from '@/lib/supabase/server'

const RAILWAY_API_URL = process.env.NEXT_PUBLIC_RAILWAY_API_URL || 'http://localhost:3000'

/**
 * Authenticated Fetch wrapper for Railway FastAPI backend.
 * Automatically retrieves the current Supabase session and injects the JWT.
 */
export async function railwayFetch<T>(
  endpoint: string,
  options: RequestInit = {}
): Promise<T> {
  const supabase = await createClient()
  const { data: { session } } = await supabase.auth.getSession()

  if (!session) {
    throw new Error('Unauthorized: No active session found')
  }

  const url = `${RAILWAY_API_URL}${endpoint}`
  const headers = {
    'Authorization': `Bearer ${session.access_token}`,
    'Content-Type': 'application/json',
    ...options.headers,
  }

  const response = await fetch(url, {
    ...options,
    headers,
  })

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}))
    throw new Error(errorData.detail || `API Error: ${response.status} ${response.statusText}`)
  }

  return response.json()
}

/**
 * Convenience methods for common API actions.
 */
export const api = {
  getScrapeStatus: () => railwayFetch<any>('/api/scrape_status'),
  getKOLs: () => railwayFetch<{ kols: any[] }>('/api/kols'),
  getStats: () => railwayFetch<any>('/api/dashboard_stats'),
  triggerScrape: () => railwayFetch<any>('/api/trigger_manual_scrape', { method: 'POST' }),
  saveWebhooks: (data: any) => railwayFetch<any>('/api/settings/webhooks', {
    method: 'POST',
    body: JSON.stringify(data)
  })
}
