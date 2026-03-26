export interface ScrapeStatus {
  total: number
  scraped: number
  scraped_count?: number
  scraped_names: string[]
  is_running: boolean
  is_scraping?: boolean
  current_activity: string
  current_kol?: string | null
  last_updated: string | null
  last_start_at?: string | null
  next_run_at: string | null
  next_run_seconds?: number
  interval_mins?: number
  logs: string[]
}

export interface KOL {
  id: number
  name: string
  twitter_url: string
  status: 'active' | 'inactive'
  created_at: string
  last_scraped_at: string | null
}

export interface TwitterPost {
  id: number
  kol_id: number
  kol_name: string
  post_id: string
  content: string
  url: string
  posted_at: string | null
  captured_at: string
  likes: number
  reposts: number
  replies: number
  views: number
}

export interface EngagementStats {
  total_kols: number
  posts_today: number
  interactions_today: number
  connection_changes_today: number
  total_posts: number
}

export interface ApiResponse<T> {
  data: T
  error?: string
}
