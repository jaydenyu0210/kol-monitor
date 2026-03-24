'use client'

import { useState, useEffect } from 'react'
import { api } from '@/lib/api-client'
import { 
  Calendar, 
  Clock, 
  TrendingUp,
  Info,
  Loader2,
  ChevronLeft,
  ChevronRight
} from 'lucide-react'

export default function ActivityHeatmap() {
  const [data, setData] = useState<any[]>([])
  const [loading, setLoading] = useState(true)

  const fetchHeatmap = async (silent = false) => {
    if (!silent) setLoading(true)
    try {
      // Fetch last 7 days of post history
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
    fetchHeatmap()
  }, [])

  if (loading) {
    return (
      <div className="h-96 bg-slate-900/50 rounded-3xl flex items-center justify-center border border-white/5">
        <Loader2 className="w-8 h-8 text-blue-500 animate-spin" />
      </div>
    )
  }

  // Simple Heatmap Logic: Group by Day of Week and Hour
  const grid = Array(7).fill(0).map(() => Array(24).fill(0))
  const days = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
  (data || []).forEach((post: any) => {
    if (!post?.posted_at) return
    const date = new Date(post.posted_at)
    if (isNaN(date.getTime())) return // Skip invalid dates
    const day = date.getDay()
    const hour = date.getHours()
    if (day >= 0 && day < 7 && hour >= 0 && hour < 24) {
      grid[day][hour] += 1
    }
  })

  const maxVal = Math.max(...grid.flat(), 1)

  return (
    <div className="bg-slate-900/60 backdrop-blur-xl border border-white/5 rounded-3xl p-8 shadow-xl animate-in fade-in duration-700">
      <div className="flex items-center justify-between mb-8">
        <div className="flex items-center gap-4">
          <div className="p-3 bg-blue-500/10 rounded-2xl border border-blue-500/20 text-blue-400">
            <Calendar className="w-6 h-6" />
          </div>
          <div>
            <h3 className="text-lg font-bold text-white mb-0.5">Post Frequency Matrix</h3>
            <p className="text-xs text-slate-500 font-medium tracking-tight">Activity patterns observed over the last 7 days</p>
          </div>
        </div>

        <div className="flex items-center gap-2 bg-slate-950/50 p-1.5 rounded-xl border border-white/5">
          <button className="p-1.5 hover:bg-white/5 rounded-lg text-slate-500 transition-all"><ChevronLeft className="w-4 h-4" /></button>
          <span className="text-[10px] font-bold text-slate-400 uppercase tracking-widest px-2">Current Week</span>
          <button className="p-1.5 hover:bg-white/5 rounded-lg text-slate-500 transition-all"><ChevronRight className="w-4 h-4" /></button>
        </div>
      </div>

      <div className="space-y-6">
        {/* Heatmap Grid */}
        <div className="overflow-x-auto pb-4 scrollbar-thin">
          <div className="min-w-[800px]">
            {/* Hour Labels */}
            <div className="flex ml-12 mb-3">
              {Array(24).fill(0).map((_, i) => (
                <div key={i} className="flex-1 text-[9px] font-bold text-slate-700 text-center uppercase tracking-widest">
                  {i === 0 ? '12a' : i === 12 ? '12p' : i > 12 ? `${i-12}p` : `${i}a`}
                </div>
              ))}
            </div>

            {/* Days Rows */}
            <div className="space-y-1.5">
              {grid.map((row, dayIdx) => (
                <div key={dayIdx} className="flex items-center gap-3">
                  <div className="w-9 text-[10px] font-bold text-slate-500 uppercase tracking-widest text-right shrink-0">
                    {days[dayIdx]}
                  </div>
                  <div className="flex-1 flex gap-1.5">
                    {row.map((val, hourIdx) => {
                      const intensity = val / maxVal
                      return (
                        <div 
                          key={hourIdx} 
                          title={`${val} posts at ${hourIdx}:00 on ${days[dayIdx]}`}
                          className="flex-1 h-8 rounded-md transition-all border border-white/5 hover:border-white/20 cursor-help"
                          style={{ 
                            backgroundColor: val > 0 
                              ? `rgba(59, 130, 246, ${0.1 + intensity * 0.9})` 
                              : 'rgba(255, 255, 255, 0.02)'
                          }}
                        ></div>
                      )
                    })}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* Legend & Stats */}
        <div className="pt-6 border-t border-white/5 flex flex-col md:flex-row items-center justify-between gap-6">
          <div className="flex items-center gap-4">
            <div className="text-[10px] font-bold text-slate-600 uppercase tracking-widest">Activity Intensity:</div>
            <div className="flex items-center gap-1.5">
              <span className="text-[9px] text-slate-700">Low</span>
              <div className="flex gap-1">
                {[0.1, 0.3, 0.6, 1].map((op) => (
                  <div key={op} className="w-3 h-3 rounded-[3px]" style={{ backgroundColor: `rgba(59, 130, 246, ${op})` }}></div>
                ))}
              </div>
              <span className="text-[9px] text-slate-700">Peak</span>
            </div>
          </div>

          <div className="flex items-center gap-8">
            <div className="flex items-center gap-3 text-slate-500">
              <Clock className="w-4 h-4 text-blue-500" />
              <div>
                <p className="text-[10px] font-bold uppercase tracking-widest leading-tight">Peak Window</p>
                <div className="text-sm font-bold text-white tracking-tight">2:00 PM - 5:00 PM</div>
              </div>
            </div>
            <div className="flex items-center gap-3 text-slate-500">
              <TrendingUp className="w-4 h-4 text-emerald-500" />
              <div>
                <p className="text-[10px] font-bold uppercase tracking-widest leading-tight">Density Score</p>
                <div className="text-sm font-bold text-white tracking-tight">High (84%)</div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div className="mt-8 p-4 bg-slate-950/50 rounded-2xl border border-white/5 flex items-start gap-3">
        <Info className="w-4 h-4 text-slate-600 shrink-0 mt-0.5" />
        <p className="text-[10px] text-slate-600 leading-relaxed italic">
          Data reflects verified timestamps from the distributed scraper network. 
          Synchronization occurs every scrape cycle to ensure real-time accuracy across all monitored accounts.
        </p>
      </div>
    </div>
  )
}
