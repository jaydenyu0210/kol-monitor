'use client'

import { useState, useEffect } from 'react'
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
import { BarChart2, Loader2, RefreshCw } from 'lucide-react'

ChartJS.register(
  LinearScale, 
  PointElement, 
  Tooltip, 
  Legend, 
  BubbleController, 
  LogarithmicScale
)

export default function BubbleHeatmap() {
  const [data, setData] = useState<any[]>([])
  const [loading, setLoading] = useState(true)
  const [scrapeStatus, setScrapeStatus] = useState<ScrapeStatus | null>(null)

  const fetchPosts = async (silent = false) => {
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
  }

  useEffect(() => {
    fetchPosts()
  }, [])

  useEffect(() => {
    let statusTimer: ReturnType<typeof setInterval> | null = null
    let dataTimer: ReturnType<typeof setInterval> | null = null

    const fetchStatus = async () => {
      try {
        const s = await api.getScrapeStatus()
        setScrapeStatus(s)
        if (s?.is_running) {
          // While scraping, poll posts more aggressively to stream results
          if (!dataTimer) {
            dataTimer = setInterval(() => fetchPosts(true), 7000)
          }
        } else if (dataTimer) {
          clearInterval(dataTimer)
          dataTimer = null
        }
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
  }, [])

  if (loading) {
    return (
      <div className="h-96 bg-[#1e293b] rounded-xl flex items-center justify-center border border-[#334155] animate-pulse">
        <Loader2 className="w-8 h-8 text-blue-500 animate-spin" />
      </div>
    )
  }

  // Group by KOL
  const kols: Record<string, any[]> = {}
  data.forEach((p: any) => {
    if (!kols[p.kol_name]) kols[p.kol_name] = []
    kols[p.kol_name].push(p)
  })

  return (
    <div className="space-y-8 animate-in fade-in duration-500">
      <div className="flex items-center justify-between mb-4">
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
          {scrapeStatus?.is_running ? (
            <span className="text-[10px] text-amber-300 bg-amber-500/10 border border-amber-500/40 px-3 py-1.5 rounded-lg font-bold flex items-center gap-2">
              <Loader2 className="w-3 h-3 animate-spin" />
              Scraping {scrapeStatus.current_kol || 'KOLs'} ({scrapeStatus.scraped_count ?? scrapeStatus.scraped ?? 0}/{scrapeStatus.total || '?'})
            </span>
          ) : (
            <span className="text-[10px] text-slate-400 bg-slate-800/60 border border-slate-700 px-3 py-1.5 rounded-lg font-bold">
              Idle · auto-refresh each cycle
            </span>
          )}
          <button
            onClick={() => fetchPosts()}
            className="flex items-center gap-2 text-[10px] font-bold px-3 py-1.5 rounded-lg bg-[#1e293b] border border-[#334155] text-slate-300 hover:border-blue-500/40 transition-all"
            title="Refresh heatmap data"
          >
            <RefreshCw className="w-3 h-3" /> Refresh
          </button>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-8">
        {Object.keys(kols).length > 0 ? (
          Object.keys(kols).map((kolName) => (
            <KolBubbleChart key={kolName} name={kolName} posts={kols[kolName]} />
          ))
        ) : (
          <div className="text-center py-20 bg-slate-900/20 rounded-xl border border-dashed border-[#334155]">
            <p className="text-slate-600 font-medium italic">No historical posts found for heatmapping.</p>
          </div>
        )}
      </div>
    </div>
  )
}

function KolBubbleChart({ name, posts }: { name: string, posts: any[] }) {
  let maxEngagement = 0
  
  const chartData = {
    datasets: [{
      label: 'Posts',
      data: posts.map(p => {
        const views = p.views || Math.max(1, p.likes * 10)
        const engagementTotal = (p.likes || 0) + (p.reposts || 0) + (p.comments || 0) + (p.bookmarks || 0)
        const engagementRate = engagementTotal / views
        if (engagementRate > maxEngagement) maxEngagement = engagementRate

        const valueScore = (p.reposts || 0) + (p.bookmarks || 0)
        const jitter = (Math.random() - 0.5) * (views * 0.1)
        const postTime = p.posted_at || p.first_captured_at || p.captured_at

        return {
          x: new Date(postTime).getTime(),
          y: Math.max(1, views + jitter),
          r: engagementRate,
          valueScore: valueScore,
          raw: p
        }
      }),
      backgroundColor: (context: any) => {
        const val = context.raw?.valueScore || 0
        const intensity = Math.min(1, val / 50)
        const r = Math.round(59 + (239 - 59) * intensity)
        const g = Math.round(130 - (130 * intensity))
        const b = Math.round(246 - (246 * intensity))
        return `rgba(${r}, ${g}, ${b}, 0.5)`
      },
      borderColor: 'rgba(255,255,255,0.4)',
      borderWidth: 1
    }]
  }

  // Rescale radii
  chartData.datasets[0].data.forEach((d: any) => {
    let radius = d.r / (maxEngagement || 1) * 20
    if (radius < 4) radius = 4
    d.r = radius
  })

  const options: any = {
    responsive: true,
    maintainAspectRatio: false,
    onClick: (e: any, elements: any) => {
      if (elements && elements.length > 0) {
        const index = elements[0].index
        const datasetIndex = elements[0].datasetIndex
        const p = chartData.datasets[datasetIndex].data[index].raw
        if (p?.post_url) {
          window.open(p.post_url, '_blank')
        }
      }
    },
    onHover: (e: any, elements: any) => {
      const target = e.native.target
      if (target) {
        target.style.cursor = elements.length > 0 ? 'pointer' : 'default'
      }
    },
    scales: {
      x: {
        type: 'linear',
        position: 'bottom',
        ticks: {
          callback: (value: number) => new Date(value).toLocaleDateString(),
          color: '#94a3b8',
          font: { size: 10, weight: 'bold' }
        },
        grid: { color: '#334155' }
      },
      y: {
        type: 'logarithmic',
        title: { display: true, text: 'Views (Log Scale)', color: '#94a3b8', font: { size: 10, weight: 'bold' } },
        ticks: {
          color: '#94a3b8',
          font: { size: 10, weight: 'bold' },
          callback: (value: number) => {
            if (value >= 1000000) return (value / 1000000).toFixed(1) + 'M'
            if (value >= 1000) return (value / 1000).toFixed(1) + 'K'
            return value
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
            const p = context.raw.raw
            const dateStr = new Date(p.posted_at || p.first_captured_at || p.captured_at).toLocaleString()
            const viewsText = p.views ? p.views : (p.likes * 10) + ' (est.)'
            return [
              `Time: ${dateStr}`,
              `Views: ${viewsText}, Likes: ${p.likes || 0}, Reposts: ${p.reposts || 0}`,
              `Replies: ${p.comments || 0}, Bookmarks: ${p.bookmarks || 0}`,
              `Text: ${p.content ? p.content.substring(0, 50) + '...' : ''}`
            ]
          }
        }
      }
    }
  }

  return (
    <div className="bg-[#0f172a] p-6 rounded-xl border border-[#334155] shadow-inner transition-all hover:border-blue-500/30">
      <h3 className="font-bold text-lg mb-4 text-blue-400">{name}</h3>
      <div className="h-[300px]">
        <Bubble data={chartData} options={options} />
      </div>
    </div>
  )
}
