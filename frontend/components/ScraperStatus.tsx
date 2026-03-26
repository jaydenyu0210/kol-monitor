'use client'

import { useState, useEffect } from 'react'
import { clientFetch } from '@/lib/api-client'
import { ScrapeStatus } from '@/types/api'
import { 
  Play, 
  RefreshCcw, 
  Terminal, 
  CheckCircle2, 
  AlertCircle,
  Loader2
} from 'lucide-react'

export default function ScraperStatus() {
  const [status, setStatus] = useState<ScrapeStatus | null>(null)
  const [loading, setLoading] = useState(true)
  const [triggering, setTriggering] = useState(false)

  const fetchStatus = async () => {
    try {
      const data = await clientFetch<ScrapeStatus>('/api/scrape_status')
      setStatus(data)
    } catch (err) {
      console.error('Failed to fetch status', err)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchStatus()
    const interval = setInterval(fetchStatus, 3000)
    return () => clearInterval(interval)
  }, [])

  const handleTrigger = async () => {
    setTriggering(true)
    try {
      await clientFetch('/api/trigger_manual_scrape', { method: 'POST' })
      fetchStatus()
    } catch (err) {
      alert('Failed to trigger scrape')
    } finally {
      setTriggering(false)
    }
  }

  if (loading && !status) {
    return (
      <div className="h-32 bg-slate-900/50 rounded-2xl flex items-center justify-center border border-white/5">
        <Loader2 className="w-5 h-5 text-blue-500 animate-spin" />
      </div>
    )
  }

  const isScraping = !!status?.is_running || !!status?.is_scraping
  const scrapedCount = status?.scraped_count ?? status?.scraped ?? 0
  const progress = status ? (scrapedCount / (status.total || 1)) * 100 : 0

  return (
    <div className="bg-slate-900/60 backdrop-blur-xl border border-white/5 rounded-3xl p-6 shadow-xl relative overflow-hidden group">
      <div className="absolute top-0 right-0 p-6 opacity-0 group-hover:opacity-100 transition-opacity">
        <button 
          onClick={handleTrigger}
          disabled={triggering || isScraping}
          className="p-2 bg-blue-500/10 hover:bg-blue-500/20 text-blue-400 rounded-lg border border-blue-500/20 transition-all disabled:opacity-50 disabled:cursor-not-allowed shadow-[0_0_15px_rgba(59,130,246,0.1)] active:scale-95"
          title="Trigger Manual Scrape"
        >
          {triggering ? <Loader2 className="w-4 h-4 animate-spin" /> : <Play className="w-4 h-4" />}
        </button>
      </div>

      <div className="flex items-center gap-4 mb-6">
        <div className={`p-3 rounded-2xl border ${isScraping ? 'bg-blue-500/10 border-blue-500/20 text-blue-400 shadow-[0_0_20px_rgba(59,130,246,0.15)]' : 'bg-slate-950/50 border-white/5 text-slate-500'}`}>
          {isScraping ? <RefreshCcw className="w-6 h-6 animate-spin" /> : <CheckCircle2 className="w-6 h-6" />}
        </div>
        <div>
          <h3 className="text-sm font-bold text-white mb-1">Scraper Engine</h3>
          <p className="text-xs text-slate-500 font-medium tracking-tight">
            {status?.current_activity || 'System Idle'}
            {status?.current_kol ? ` · ${status.current_kol}` : ''}
          </p>
        </div>
      </div>

      {isScraping && (
        <div className="space-y-4 mb-6">
          <div className="flex justify-between text-[10px] font-bold text-slate-600 uppercase tracking-widest">
            <span>Progress: {scrapedCount} / {status.total}</span>
            <span>{Math.round(progress)}%</span>
          </div>
          <div className="h-1.5 w-full bg-slate-950 rounded-full overflow-hidden border border-white/5">
            <div 
              className="h-full bg-blue-500 rounded-full transition-all duration-1000 shadow-[0_0_15px_rgba(59,130,246,0.5)]"
              style={{ width: `${progress}%` }}
            ></div>
          </div>
        </div>
      )}

      {/* Terminal Logs View */}
      <div className="mt-4 bg-slate-950/80 rounded-2xl border border-white/5 p-4 font-mono text-[10px] text-slate-500 h-32 overflow-y-auto scrollbar-thin">
        <div className="flex items-center gap-2 mb-3 text-slate-600 border-b border-white/5 pb-2">
          <Terminal className="w-3 h-3" />
          <span className="font-bold tracking-widest uppercase">System Activity Console</span>
        </div>
        <div className="space-y-1">
          {status?.logs && status.logs.length > 0 ? (
            status.logs.map((log, i) => (
              <div key={i} className="flex gap-2">
                <span className="text-blue-500/50">›</span>
                <span className={log.includes('🏁') || log.includes('✅') ? 'text-blue-400' : ''}>{log}</span>
              </div>
            ))
          ) : (
            <div className="text-slate-800 italic">No activity recorded for this session</div>
          )}
        </div>
      </div>
    </div>
  )
}
