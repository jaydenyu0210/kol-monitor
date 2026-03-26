'use client'

import { useState, useEffect, useRef } from 'react'
import { api } from '@/lib/api-client'
import { Clock, Loader2 } from 'lucide-react'
import { ScrapeStatus } from '@/types/api'

export default function ScrapeTimer() {
  const [timeLeft, setTimeLeft] = useState<string>('--:--')
  const [status, setStatus] = useState<(ScrapeStatus & { fetchedAt: number }) | null>(null)
  const prevRunningRef = useRef<boolean>(false)

  useEffect(() => {
    const fetchStatus = async () => {
      try {
        const data = await api.getScrapeStatus()
        setStatus({ ...data, fetchedAt: Date.now() })
      } catch (err) {
        console.error('Failed to fetch scrape status', err)
      }
    }

    fetchStatus()
    const pollInterval = setInterval(fetchStatus, 10000) // Poll every 10s
    return () => clearInterval(pollInterval)
  }, [])

  useEffect(() => {
    if (!status) return

    // Auto-refresh logic: if we transitions from running to not running
    if (prevRunningRef.current === true && status.is_running === false) {
      console.log('Scrape finished. Auto-refreshing...')
      window.location.reload()
    }
    prevRunningRef.current = !!status.is_running
  }, [status])

  useEffect(() => {
    if (!status) return

    const timerInterval = setInterval(() => {
      const now = Date.now()
      const intervalMs = Math.max(1, (status.interval_mins || 5) * 60 * 1000)
      let remainingMs = 0

      if (status.next_run_seconds !== undefined && status.next_run_seconds !== null) {
        const elapsedSinceFetch = Math.floor((now - status.fetchedAt) / 1000)
        remainingMs = Math.max(0, (status.next_run_seconds - elapsedSinceFetch) * 1000)
      }

      if (remainingMs === 0 && status.last_updated) {
        const lastScrapeTime = new Date(status.last_updated).getTime()
        const timeSinceScrape = Math.max(0, now - lastScrapeTime)
        remainingMs = intervalMs - (timeSinceScrape % intervalMs)
      }

      const totalSeconds = Math.floor(remainingMs / 1000)
      const m = Math.floor(totalSeconds / 60)
      const s = totalSeconds % 60
      setTimeLeft(`${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`)
    }, 1000)

    return () => clearInterval(timerInterval)
  }, [status])

  const isRunning = !!status?.is_running || !!status?.is_scraping
  const scrapedCount = status?.scraped_count ?? status?.scraped ?? 0
  const totalKols = status?.total ?? 0
  const currentKol = status?.current_kol
  const activityLabel = isRunning
    ? `Scraping ${currentKol || 'KOLs'} (${scrapedCount}/${totalKols || '?'})`
    : 'Idle'

  return (
    <div className="flex items-center gap-3">
      {isRunning && status?.current_activity && (
        <span className="text-[10px] text-blue-400 bg-blue-500/10 px-3 py-1.5 rounded-lg border border-blue-500/20 flex items-center gap-2 font-bold animate-pulse">
          <Loader2 className="w-3 h-3 animate-spin" />
          {status.current_activity}
        </span>
      )}

      {!isRunning && (
        <span className="text-[10px] text-slate-400 bg-[#1e293b] px-3 py-1.5 rounded-lg border border-[#334155] flex items-center gap-1.5 font-medium">
          <Clock className="w-3 h-3 text-blue-400" />
          {status?.last_updated ? `Last Scrape: ${new Date(status.last_updated).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}` : 'Idle · waiting for next cycle'}
        </span>
      )}

      <span className={`text-[10px] px-3 py-1.5 rounded-lg border font-bold ${isRunning ? 'text-orange-300 bg-orange-500/10 border-orange-500/30' : 'text-slate-400 bg-slate-800/50 border-slate-700/70'}`}>
        {activityLabel}
      </span>

      <div className="bg-blue-900/10 border border-blue-900/40 px-3 py-1.5 rounded-lg flex items-center gap-2">
        <span className="text-[9px] text-blue-400/80 uppercase font-bold tracking-wider">Next cycle in:</span>
        <span className="text-xs font-mono text-blue-300 font-bold w-10 text-center">{timeLeft}</span>
      </div>
    </div>
  )
}
