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
  heatmap_finished_at?: string | null
  next_run_at: string | null
  next_run_seconds?: number
  interval_mins?: number
  logs: string[]
  kol_timings?: Record<string, { started_at: string; elapsed_s: number | null; posts: number | null; error?: string }>
}

export interface NewPostEntry {
  kol_name: string
  post_id: string
  content: string
  posted_at: string
  scraped_at: string
  post_url: string
  likes: number
  reposts: number
  comments: number
  views: number
  bookmarks: number
}

export interface NewPostsScrapeStatus {
  is_running: boolean
  current_activity: string | null
  current_kol: string | null
  total_kols: number
  scraped_count: number
  last_start_at: string | null
  cutoff_time: string | null
  finished_at: string | null
  next_run_at: string | null
  next_run_seconds: number
  new_posts_count: number
  new_posts: NewPostEntry[]
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
