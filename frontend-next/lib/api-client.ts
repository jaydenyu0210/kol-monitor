import { createClient } from '@/lib/supabase/client'

const RAILWAY_API_URL = process.env.NEXT_PUBLIC_RAILWAY_API_URL || 'http://localhost:3000'

export async function clientFetch<T>(
  endpoint: string,
  options: RequestInit = {}
): Promise<T> {
  const supabase = createClient()
  const { data: { session } } = await supabase.auth.getSession()

  if (!session) {
    throw new Error('Unauthorized')
  }

  const response = await fetch(`${RAILWAY_API_URL}${endpoint}`, {
    ...options,
    headers: {
      'Authorization': `Bearer ${session.access_token}`,
      'Content-Type': 'application/json',
      ...options.headers,
    },
  })

  if (!response.ok) {
    throw new Error('API Error')
  }

  return response.json()
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
