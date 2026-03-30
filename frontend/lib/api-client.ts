import { createClient } from '@/lib/supabase/client'

async function clientFetchOnce<T>(endpoint: string, options: RequestInit, token: string): Promise<T> {
  const response = await fetch(endpoint, {
    ...options,
    headers: {
      'Authorization': `Bearer ${token}`,
      'Content-Type': 'application/json',
      ...options.headers,
    },
  })

  if (!response.ok) {
    throw new Error(`API Error ${response.status}`)
  }

  return response.json()
}

export async function clientFetch<T>(
  endpoint: string,
  options: RequestInit = {}
): Promise<T> {
  const supabase = createClient()
  const { data: { session } } = await supabase.auth.getSession()

  if (!session) {
    throw new Error('Unauthorized')
  }

  const token = session.access_token

  // Retry once on connection errors (ECONNRESET / network glitches during Docker startup)
  try {
    return await clientFetchOnce<T>(endpoint, options, token)
  } catch (err: any) {
    const isConnectionError = err?.message === 'Failed to fetch' || err?.message?.includes('fetch') || err?.message?.startsWith('API Error 5')
    if (isConnectionError) {
      await new Promise(r => setTimeout(r, 1500))
      return await clientFetchOnce<T>(endpoint, options, token)
    }
    throw err
  }
}

export const api = {
  getSettings: () => clientFetch<any>('/api/settings'),
  saveWebhooks: (data: any) => clientFetch<any>('/api/settings/webhooks', {
    method: 'POST',
    body: JSON.stringify(data)
  }),
  getOverviewFeed: () => clientFetch<any>('/api/overview_feed'),
  getPostHistory: (params: string = '') => clientFetch<any>(`/api/discord_posts_history${params}`),
  getKOLs: () => clientFetch<{ kols: any[] }>('/api/kols'),
  addKOL: (name: string, twitter_url: string) => clientFetch<any>('/api/kols', {
    method: 'POST',
    body: JSON.stringify({ name, twitter_url })
  }),
  deleteKOL: (id: number) => clientFetch<any>(`/api/kols/${id}`, { method: 'DELETE' }),
  saveCookies: (data: { auth_token: string, ct0: string }) => clientFetch<any>('/api/settings/cookies', {
    method: 'POST',
    body: JSON.stringify(data)
  }),
  getScrapeStatus: () => clientFetch<any>('/api/scrape_status')
}
