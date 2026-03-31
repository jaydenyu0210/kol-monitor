'use client'

import { useState, useEffect, useRef } from 'react'
import { api } from '@/lib/api-client'
import { Clock, Loader2, Radio } from 'lucide-react'
import { NewPostsScrapeStatus } from '@/types/api'

export default function ScrapeTimer() {
  const [timeLeft, setTimeLeft] = useState<string>('--:--')
  const [status, setStatus] = useState<(NewPostsScrapeStatus & { fetchedAt: number }) | null>(null)
  const prevRunningRef = useRef<boolean>(false)

  useEffect(() => {
    const fetchStatus = async () => {
      try {
        const data = await api.getNewPostsScrapeStatus()
        setStatus({ ...data, fetchedAt: Date.now() })
      } catch (err) {
        console.error('Failed to fetch new posts scrape status', err)
      }
    }

    fetchStatus()
    const pollInterval = setInterval(fetchStatus, 10000)
    return () => clearInterval(pollInterval)
  }, [])

  useEffect(() => {
    if (!status) return
    if (prevRunningRef.current === true && status.is_running === false) {
      console.log('New posts scan finished.')
    }
    prevRunningRef.current = !!status.is_running
  }, [status])

  useEffect(() => {
    if (!status) return

    const timerInterval = setInterval(() => {
      if (status.is_running) {
        setTimeLeft('⏳')
        return
      }

      if (status.next_run_seconds !== undefined && status.next_run_seconds > 0) {
        const elapsedSinceFetch = Math.floor((Date.now() - status.fetchedAt) / 1000)
        const remainingS = Math.max(0, status.next_run_seconds - elapsedSinceFetch)
        const m = Math.floor(remainingS / 60)
        const s = remainingS % 60
        setTimeLeft(`${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`)
      } else {
        setTimeLeft('00:00')
      }
    }, 1000)

    return () => clearInterval(timerInterval)
  }, [status])

  const isRunning = !!status?.is_running
  const scrapedCount = status?.scraped_count ?? 0
  const totalKols = status?.total_kols ?? 0
  const currentKol = status?.current_kol
  const activityLabel = isRunning
    ? `Scanning ${currentKol || 'KOLs'} (${scrapedCount}/${totalKols || '?'})`
    : 'Idle'

  return (
    <div className="flex items-center gap-3">
      {isRunning && (
        <span className="text-[10px] text-green-400 bg-green-500/10 px-3 py-1.5 rounded-lg border border-green-500/20 flex items-center gap-2 font-bold animate-pulse">
          <Radio className="w-3 h-3" />
          New Posts: {status?.current_activity || activityLabel}
        </span>
      )}

      {!isRunning && (
        <span className="text-[10px] text-slate-400 bg-[#1e293b] px-3 py-1.5 rounded-lg border border-[#334155] flex items-center gap-1.5 font-medium">
          <Clock className="w-3 h-3 text-green-400" />
          {status?.finished_at
            ? `Last scan: ${new Date(status.finished_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}`
            : 'New posts scanner idle'}
        </span>
      )}

      <span className={`text-[10px] px-3 py-1.5 rounded-lg border font-bold ${isRunning ? 'text-green-300 bg-green-500/10 border-green-500/30' : 'text-slate-400 bg-slate-800/50 border-slate-700/70'}`}>
        {activityLabel}
      </span>

      <div className="bg-green-900/10 border border-green-900/40 px-3 py-1.5 rounded-lg flex items-center gap-2">
        <span className="text-[9px] text-green-400/80 uppercase font-bold tracking-wider">
          {isRunning ? 'Scanning' : 'Next scan in:'}
        </span>
        <span className="text-xs font-mono text-green-300 font-bold w-10 text-center">{timeLeft}</span>
      </div>
    </div>
  )
}
