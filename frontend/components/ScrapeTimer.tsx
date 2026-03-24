'use client'

import { useState, useEffect, useRef } from 'react'
import { api } from '@/lib/api-client'
import { Clock, Loader2 } from 'lucide-react'

export default function ScrapeTimer() {
  const [timeLeft, setTimeLeft] = useState<string>('--:--')
  const [status, setStatus] = useState<any>(null)
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
      let remainingMs = 0
      // We hardcode this to 5 minutes to override any stale data from ghost instances
      const intervalSeconds = 30 * 60 
      const intervalMs = intervalSeconds * 1000
      
      if (status.next_run_seconds !== undefined) {
        // next_run_seconds is the remaining time calculated by the server.
        // We subtract the time elapsed since the status was fetched.
        const timeSinceFetch = Math.floor((now - status.fetchedAt) / 1000)
        remainingMs = Math.max(0, (status.next_run_seconds - timeSinceFetch) * 1000)
        
        // Safety cap: if the server-calculated remaining time is somehow larger than the interval
        if (remainingMs > intervalMs) {
           const lastScrapeTime = new Date(status.last_updated).getTime()
           const timeSinceScrape = Math.max(0, now - lastScrapeTime)
           remainingMs = intervalMs - (timeSinceScrape % intervalMs)
        }
      } else {
        // Fallback to estimation based on last scrape and interval
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

  return (
    <div className="flex items-center gap-3">
      {status?.is_running && status?.current_activity && (
        <span className="text-[10px] text-blue-400 bg-blue-500/10 px-3 py-1.5 rounded-lg border border-blue-500/20 flex items-center gap-2 font-bold animate-pulse">
          <Loader2 className="w-3 h-3 animate-spin" />
          {status.current_activity}
        </span>
      )}

      {status?.last_updated && !status?.is_running && (
        <span className="text-[10px] text-slate-400 bg-[#1e293b] px-3 py-1.5 rounded-lg border border-[#334155] flex items-center gap-1.5 font-medium">
          <Clock className="w-3 h-3 text-blue-400" />
          Last Scrape: {new Date(status.last_updated).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
        </span>
      )}
      
      <div className="bg-blue-900/10 border border-blue-900/40 px-3 py-1.5 rounded-lg flex items-center gap-2">
        <span className="text-[9px] text-blue-400/80 uppercase font-bold tracking-wider">Next cycle in:</span>
        <span className="text-xs font-mono text-blue-300 font-bold w-10 text-center">{timeLeft}</span>
      </div>
    </div>
  )
}
