'use client'

import { useState, useEffect, useRef, useCallback, useMemo } from 'react'
import { api } from '@/lib/api-client'
import { ScrapeStatus } from '@/types/api'
import {
  Chart as ChartJS,
  LinearScale,
  PointElement,
  Tooltip,
  Legend,
  BubbleController,
  LogarithmicScale
} from 'chart.js'
import { Bubble } from 'react-chartjs-2'
import { BarChart2, Loader2, RefreshCw, CheckCircle2, Clock, Radio, Timer, AlertCircle, Play } from 'lucide-react'

ChartJS.register(
  LinearScale,
  PointElement,
  Tooltip,
  Legend,
  BubbleController,
  LogarithmicScale
)

type KolStatus = 'idle' | 'scraping' | 'done' | 'pending'

// Stable jitter per post_id so bubbles don't jump on re-render
const jitterCache: Record<string, number> = {}
function stableJitter(postId: string): number {
  if (!(postId in jitterCache)) {
    jitterCache[postId] = (Math.random() - 0.5)
  }
  return jitterCache[postId]
}

function formatElapsed(seconds: number): string {
  if (seconds < 60) return `${Math.round(seconds)}s`
  const m = Math.floor(seconds / 60)
  const s = Math.round(seconds % 60)
  return `${m}m ${s}s`
}

function getBubbleColor(valueScore: number, isNew: boolean, isPending: boolean): string {
  if (isNew) {
    const intensity = Math.min(1, valueScore / 50)
    const r = Math.round(34 + (100 * intensity))
    const g = Math.round(197 + (58 * intensity))
    const b = Math.round(94 - (44 * intensity))
    return `rgba(${r}, ${g}, ${b}, 0.75)`
  }
  if (isPending) return 'rgba(100, 116, 139, 0.25)'
  const intensity = Math.min(1, valueScore / 50)
  const r = Math.round(59 + (239 - 59) * intensity)
  const g = Math.round(130 - (130 * intensity))
  const b = Math.round(246 - (246 * intensity))
  return `rgba(${r}, ${g}, ${b}, 0.5)`
}

function getBubbleBorder(isNew: boolean, isPending: boolean): string {
  if (isNew) return 'rgba(74, 222, 128, 0.9)'
  if (isPending) return 'rgba(100, 116, 139, 0.3)'
  return 'rgba(255,255,255,0.3)'
}

export default function BubbleHeatmap() {
  const [data, setData] = useState<any[]>([])
  const [loading, setLoading] = useState(true)
  const [scrapeStatus, setScrapeStatus] = useState<ScrapeStatus | null>(null)
  const [scrapedKolIds, setScrapedKolIds] = useState<Set<string>>(new Set())

  const fetchPosts = useCallback(async (silent = false) => {
    if (!silent) setLoading(true)
    try {
      const resp = await api.getPostHistory('?days=7&sort=recent')
      const posts = Array.isArray(resp) ? resp : (resp?.posts || [])
      setData(posts)
    } catch (err) {
      console.error('Failed to fetch heatmap data', err)
    } finally {
      if (!silent) setLoading(false)
    }
  }, [])

  useEffect(() => { fetchPosts() }, [fetchPosts])

  const prevRunning = useRef(false)
  useEffect(() => {
    const isRunning = !!scrapeStatus?.is_running
    if (isRunning && !prevRunning.current) {
      setScrapedKolIds(new Set())
    }
    if (!isRunning && prevRunning.current) {
      const t = setTimeout(() => {
        setScrapedKolIds(new Set())
      }, 10000)
      prevRunning.current = isRunning
      return () => clearTimeout(t)
    }
    prevRunning.current = isRunning
  }, [scrapeStatus?.is_running])

  useEffect(() => {
    if (!scrapeStatus?.is_running) return
    const names = scrapeStatus.scraped_names || []
    if (names.length > 0) setScrapedKolIds(new Set(names))
  }, [scrapeStatus?.scraped_names, scrapeStatus?.is_running])

  useEffect(() => {
    let statusTimer: ReturnType<typeof setInterval> | null = null
    let dataTimer: ReturnType<typeof setInterval> | null = null
    let wasRunning = false

    const fetchStatus = async () => {
      try {
        const s = await api.getScrapeStatus()
        setScrapeStatus(s)
        const running = !!s?.is_running
        if (running && !wasRunning) {
          if (dataTimer) clearInterval(dataTimer)
          dataTimer = setInterval(() => fetchPosts(true), 5000)
          if (statusTimer) clearInterval(statusTimer)
          statusTimer = setInterval(fetchStatus, 4000)
        } else if (!running && wasRunning) {
          fetchPosts(true)
          if (dataTimer) { clearInterval(dataTimer); dataTimer = null }
          if (statusTimer) clearInterval(statusTimer)
          statusTimer = setInterval(fetchStatus, 10000)
        }
        wasRunning = running
      } catch (err) {
        console.error('Failed to fetch scrape status', err)
      }
    }

    fetchStatus()
    statusTimer = setInterval(fetchStatus, 10000)
    return () => {
      if (statusTimer) clearInterval(statusTimer)
      if (dataTimer) clearInterval(dataTimer)
    }
  }, [fetchPosts])

  const getKolStatus = useCallback((kolName: string): KolStatus => {
    if (!scrapeStatus?.is_running) return 'idle'
    if (scrapeStatus.current_kol === kolName) return 'scraping'
    if ((scrapeStatus.scraped_names || []).includes(kolName)) return 'done'
    return 'pending'
  }, [scrapeStatus])

  if (loading) {
    return (
      <div className="h-96 bg-[#1e293b] rounded-xl flex items-center justify-center border border-[#334155] animate-pulse">
        <Loader2 className="w-8 h-8 text-blue-500 animate-spin" />
      </div>
    )
  }

  const kols: Record<string, any[]> = {}
  data.forEach((p: any) => {
    const name = p.kol_name || p.kol
    if (!kols[name]) kols[name] = []
    kols[name].push(p)
  })

  const kolNames = Object.keys(kols)
  const isRunning = !!scrapeStatus?.is_running
  const scrapedCount = scrapeStatus?.scraped_count ?? scrapeStatus?.scraped ?? 0
  const totalKols = scrapeStatus?.total || kolNames.length
  const progressPct = isRunning && totalKols > 0 ? Math.round((scrapedCount / totalKols) * 100) : 0
  const kolTimings = scrapeStatus?.kol_timings || {}
  const isScrapeActive = isRunning || scrapedKolIds.size > 0
  const scrapeStartAt = scrapeStatus?.last_start_at ? new Date(scrapeStatus.last_start_at).getTime() : null

  // Manual scrape button cooldown: disabled for 30 min after heatmap_finished_at
  const COOLDOWN_MINS = 30
  const finishedAt = scrapeStatus?.heatmap_finished_at ? new Date(scrapeStatus.heatmap_finished_at).getTime() : null
  const cooldownRemaining = finishedAt ? Math.max(0, COOLDOWN_MINS * 60 * 1000 - (Date.now() - finishedAt)) : 0
  const isOnCooldown = cooldownRemaining > 0
  const cooldownMins = Math.ceil(cooldownRemaining / 60000)
  const canTrigger = !isRunning && !isOnCooldown

  const handleManualScrape = async () => {
    if (!canTrigger) return
    try {
      await api.triggerManualScrape()
    } catch (err) {
      console.error('Failed to trigger scrape', err)
    }
  }

  return (
    <div className="space-y-6 animate-in fade-in duration-500">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-bold flex items-center text-white gap-2">
            <BarChart2 className="w-5 h-5 text-blue-400" />
            Historical X KOL Posts (Bubble Heatmap)
          </h2>
          <p className="text-xs text-slate-400 mt-1">
            <b>X-Axis:</b> Timeline | <b>Y-Axis:</b> Views | <b>Bubble Size:</b> Engagement Rate | <b>Bubble Color:</b> Reposts + Bookmarks
          </p>
        </div>
        <div className="flex items-center gap-2">
          {isRunning ? (
            <span className="text-[10px] text-amber-300 bg-amber-500/10 border border-amber-500/40 px-3 py-1.5 rounded-lg font-bold flex items-center gap-2">
              <Loader2 className="w-3 h-3 animate-spin" />
              Live Scraping {scrapeStatus?.current_kol || ''} ({scrapedCount}/{totalKols})
            </span>
          ) : isOnCooldown ? (
            <span className="text-[10px] text-slate-500 bg-slate-800/60 border border-slate-700 px-3 py-1.5 rounded-lg font-bold flex items-center gap-1.5">
              <Clock className="w-3 h-3" />
              Cooldown: {cooldownMins}m remaining
            </span>
          ) : (
            <span className="text-[10px] text-slate-400 bg-slate-800/60 border border-slate-700 px-3 py-1.5 rounded-lg font-bold">
              Ready to scrape
            </span>
          )}
          <button
            onClick={handleManualScrape}
            disabled={!canTrigger}
            className={`flex items-center gap-2 text-[10px] font-bold px-3 py-1.5 rounded-lg border transition-all ${
              canTrigger
                ? 'bg-blue-600 border-blue-500 text-white hover:bg-blue-500 cursor-pointer'
                : 'bg-slate-800/50 border-slate-700 text-slate-600 cursor-not-allowed'
            }`}
          >
            <Play className="w-3 h-3" /> Scrape Heatmap
          </button>
          <button
            onClick={() => fetchPosts()}
            className="flex items-center gap-2 text-[10px] font-bold px-3 py-1.5 rounded-lg bg-[#1e293b] border border-[#334155] text-slate-300 hover:border-blue-500/40 transition-all"
          >
            <RefreshCw className="w-3 h-3" /> Refresh
          </button>
        </div>
      </div>

      {isRunning && (
        <div className="space-y-2">
          <div className="flex items-center justify-between text-[10px] text-slate-400">
            <span className="flex items-center gap-1.5">
              <Radio className="w-3 h-3 text-green-400 animate-pulse" />
              Scraping in progress — bubbles appear live as posts are captured
            </span>
            <span className="font-mono">{scrapedCount}/{totalKols} KOLs · {progressPct}%</span>
          </div>
          <div className="w-full h-1.5 bg-slate-800 rounded-full overflow-hidden">
            <div
              className="h-full bg-gradient-to-r from-blue-500 to-cyan-400 rounded-full transition-all duration-700 ease-out"
              style={{ width: `${progressPct}%` }}
            />
          </div>
        </div>
      )}

      <div className="grid grid-cols-1 gap-8">
        {kolNames.length > 0 ? (
          kolNames.map((kolName) => {
            const kolStatus = getKolStatus(kolName)
            const allPosts = kols[kolName]

            // During scraping: filter posts to only show those captured in this cycle
            let filteredPosts: any[]
            if (isScrapeActive && scrapeStartAt) {
              if (kolStatus === 'pending') {
                filteredPosts = [] // pending KOLs show empty
              } else {
                // done or scraping: only posts captured during this scrape cycle
                filteredPosts = allPosts.filter((p: any) => {
                  const capturedAt = new Date(p.captured_at).getTime()
                  return capturedAt >= scrapeStartAt
                })
              }
            } else {
              filteredPosts = allPosts // idle: show all
            }

            return (
              <KolBubbleChart
                key={kolName}
                name={kolName}
                posts={filteredPosts}
                status={kolStatus}
                timing={kolTimings[kolName]}
                isScrapeActive={isScrapeActive}
              />
            )
          })
        ) : (
          <div className="text-center py-20 bg-slate-900/20 rounded-xl border border-dashed border-[#334155]">
            <p className="text-slate-600 font-medium italic">No historical posts found for heatmapping.</p>
          </div>
        )}
      </div>
    </div>
  )
}

function KolBubbleChart({ name, posts, status, timing, isScrapeActive }: {
  name: string
  posts: any[]
  status: KolStatus
  timing?: { started_at: string; elapsed_s: number | null; posts: number | null; error?: string }
  isScrapeActive: boolean
}) {
  const [liveElapsed, setLiveElapsed] = useState<number | null>(null)

  useEffect(() => {
    if (status !== 'scraping' || !timing?.started_at) {
      setLiveElapsed(null)
      return
    }
    const startTime = new Date(timing.started_at).getTime()
    const tick = () => setLiveElapsed(Math.round((Date.now() - startTime) / 1000))
    tick()
    const interval = setInterval(tick, 1000)
    return () => clearInterval(interval)
  }, [status, timing?.started_at])

  const isLive = isScrapeActive && (status === 'done' || status === 'scraping')

  // Build chart data with pre-computed colors and static values (no scriptable options)
  const chartData = useMemo(() => {
    let maxEng = 0
    const processed: any[] = []

    for (const p of posts) {
      const rawViews = p.views || 0
      const views = rawViews > 0 ? rawViews : Math.max(10, (p.likes || 0) * 10)
      const engagementTotal = (p.likes || 0) + (p.reposts || 0) + (p.comments || 0) + (p.bookmarks || 0)
      const engagementRate = views > 0 ? engagementTotal / views : 0
      if (engagementRate > maxEng) maxEng = engagementRate

      const valueScore = (p.reposts || 0) + (p.bookmarks || 0)
      const postTime = p.posted_at || p.first_captured_at || p.captured_at
      const xVal = postTime ? new Date(postTime).getTime() : null
      if (!xVal || isNaN(xVal)) continue // skip invalid dates

      const jitter = stableJitter(p.post_id) * (views * 0.05)

      processed.push({
        x: xVal,
        y: Math.max(10, views + jitter), // minimum 10 for log scale
        engRate: engagementRate,
        valueScore,
        isNew: isLive,
        raw: p
      })
    }

    // Rescale radii and pre-compute colors
    const bgColors: string[] = []
    const borderColors: string[] = []
    const borderWidths: number[] = []

    for (const d of processed) {
      let radius = maxEng > 0 ? (d.engRate / maxEng) * 15 : 4
      if (radius < 3) radius = 3
      if (radius > 15) radius = 15
      d.r = radius
      delete d.engRate

      bgColors.push(getBubbleColor(d.valueScore, d.isNew, false))
      borderColors.push(getBubbleBorder(d.isNew, false))
      borderWidths.push(d.isNew ? 2 : 1)
    }

    return {
      datasets: [{
        label: 'Posts',
        data: processed,
        backgroundColor: bgColors,
        borderColor: borderColors,
        borderWidth: borderWidths,
      }]
    }
  }, [posts, isLive])

  const options: any = useMemo(() => ({
    responsive: true,
    maintainAspectRatio: false,
    animation: { duration: 300 },
    onClick: (_e: any, elements: any) => {
      if (elements?.length > 0) {
        const p = chartData.datasets[0].data[elements[0].index]?.raw
        if (p?.post_url) window.open(p.post_url, '_blank')
      }
    },
    onHover: (e: any, elements: any) => {
      const target = e.native?.target
      if (target) target.style.cursor = elements.length > 0 ? 'pointer' : 'default'
    },
    scales: {
      x: {
        type: 'linear' as const,
        position: 'bottom' as const,
        ticks: {
          callback: (value: number) => new Date(value).toLocaleDateString(),
          color: '#94a3b8',
          font: { size: 10, weight: 'bold' as const }
        },
        grid: { color: '#334155' }
      },
      y: {
        type: 'logarithmic' as const,
        min: 10,
        title: { display: true, text: 'Views (Log Scale)', color: '#94a3b8', font: { size: 10, weight: 'bold' as const } },
        ticks: {
          color: '#94a3b8',
          font: { size: 10, weight: 'bold' as const },
          callback: (value: number) => {
            if (value >= 1000000) return (value / 1000000).toFixed(1) + 'M'
            if (value >= 1000) return (value / 1000).toFixed(1) + 'K'
            return value.toString()
          }
        },
        grid: { color: '#334155' }
      }
    },
    plugins: {
      legend: { display: false },
      tooltip: {
        callbacks: {
          label: (context: any) => {
            const p = context.raw?.raw
            if (!p) return ''
            const dateStr = new Date(p.posted_at || p.first_captured_at || p.captured_at).toLocaleString()
            const viewsText = p.views || `${(p.likes || 0) * 10} (est.)`
            const tag = context.raw.isNew ? ' [NEW]' : ''
            return [
              `Time: ${dateStr}${tag}`,
              `Views: ${viewsText}, Likes: ${p.likes || 0}, Reposts: ${p.reposts || 0}`,
              `Replies: ${p.comments || 0}, Bookmarks: ${p.bookmarks || 0}`,
              `Text: ${p.content ? p.content.substring(0, 50) + '...' : ''}`
            ]
          }
        }
      }
    }
  }), [chartData])

  const borderClass =
    status === 'scraping' ? 'border-amber-500/60 shadow-[0_0_15px_rgba(245,158,11,0.15)]' :
    status === 'done' ? 'border-green-500/40' :
    status === 'pending' ? 'border-slate-700/50 opacity-60' :
    'border-[#334155]'

  const elapsedDisplay = status === 'scraping' && liveElapsed !== null
    ? formatElapsed(liveElapsed)
    : timing?.elapsed_s != null
      ? formatElapsed(timing.elapsed_s)
      : null

  return (
    <div className={`bg-[#0f172a] p-6 rounded-xl border shadow-inner transition-all duration-500 ${borderClass} hover:border-blue-500/30`}>
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-3">
          <h3 className="font-bold text-lg text-blue-400">{name}</h3>
          <span className="text-[10px] text-slate-500 font-mono">{posts.length} posts</span>
        </div>
        <div className="flex items-center gap-2">
          {elapsedDisplay && (
            <span className={`text-[10px] font-mono px-2 py-0.5 rounded flex items-center gap-1 ${
              status === 'scraping'
                ? 'text-amber-300 bg-amber-500/10 border border-amber-500/20'
                : timing?.error
                  ? 'text-red-400 bg-red-500/10 border border-red-500/20'
                  : 'text-slate-400 bg-slate-800/50 border border-slate-700/50'
            }`}>
              <Timer className="w-3 h-3" />
              {elapsedDisplay}
            </span>
          )}
          <KolStatusBadge status={status} error={timing?.error} />
        </div>
      </div>
      <div className="h-[300px] relative">
        <Bubble data={chartData} options={options} />
        {posts.length === 0 && (
          <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
            {status === 'pending' ? (
              <p className="text-xs text-slate-600 italic flex items-center gap-2">
                <Clock className="w-4 h-4" /> Waiting to scrape...
              </p>
            ) : status === 'scraping' ? (
              <p className="text-xs text-slate-500 flex items-center gap-2">
                <Loader2 className="w-4 h-4 text-amber-400 animate-spin" /> Scraping — bubbles will appear as posts are found
              </p>
            ) : (
              <p className="text-xs text-slate-600 italic">No posts in the last 7 days</p>
            )}
          </div>
        )}
      </div>
    </div>
  )
}

function KolStatusBadge({ status, error }: { status: KolStatus; error?: string }) {
  switch (status) {
    case 'scraping':
      return (
        <span className="text-[10px] text-amber-300 bg-amber-500/10 border border-amber-500/30 px-2.5 py-1 rounded-lg font-bold flex items-center gap-1.5 animate-pulse">
          <Loader2 className="w-3 h-3 animate-spin" />
          Scraping...
        </span>
      )
    case 'done':
      return error ? (
        <span className="text-[10px] text-red-400 bg-red-500/10 border border-red-500/30 px-2.5 py-1 rounded-lg font-bold flex items-center gap-1.5">
          <AlertCircle className="w-3 h-3" />
          {error === 'timeout' ? 'Timed out' : 'Error'}
        </span>
      ) : (
        <span className="text-[10px] text-green-400 bg-green-500/10 border border-green-500/30 px-2.5 py-1 rounded-lg font-bold flex items-center gap-1.5">
          <CheckCircle2 className="w-3 h-3" />
          Updated
        </span>
      )
    case 'pending':
      return (
        <span className="text-[10px] text-slate-500 bg-slate-800/50 border border-slate-700/50 px-2.5 py-1 rounded-lg font-bold flex items-center gap-1.5">
          <Clock className="w-3 h-3" />
          Pending
        </span>
      )
    default:
      return null
  }
}
