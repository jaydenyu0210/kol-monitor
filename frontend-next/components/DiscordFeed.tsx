'use client'

import { useState, useEffect } from 'react'
import { api } from '@/lib/api-client'
import { 
  MessageSquare, 
  Flame, 
  Zap, 
  ExternalLink,
  Clock,
  Loader2
} from 'lucide-react'

export default function DiscordFeed() {
  const [data, setData] = useState<any>(null)
  const [loading, setLoading] = useState(true)

  const fetchData = async () => {
    try {
      const result = await api.getOverviewFeed()
      setData(result)
    } catch (err) {
      console.error('Failed to fetch Discord feed', err)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchData()
    const interval = setInterval(fetchData, 15000)
    return () => clearInterval(interval)
  }, [])

  if (loading && !data) {
    return (
      <div className="flex justify-center py-20">
        <Loader2 className="w-8 h-8 text-blue-500 animate-spin" />
      </div>
    )
  }

  const truncate = (str: string, len: number) => {
    if (!str) return ''
    return str.length > len ? str.substring(0, len) + '...' : str
  }

  const formatDelta = (val: number) => (val > 0 ? `+${val.toLocaleString()}` : val.toLocaleString())

  const formatRange = (meta: any) => {
    if (!meta?.start_time || !meta?.end_time) return ""
    const s = new Date(meta.start_time).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', hour12: true })
    const e = new Date(meta.end_time).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', hour12: true })
    return `from ${s} to ${e}`
  }

  const recentPosts = data?.recent_posts?.items || (Array.isArray(data?.recent_posts) ? data.recent_posts : [])
  const recentMeta = data?.recent_posts?.metadata
  const hotPosts = data?.hot_posts?.items || (Array.isArray(data?.hot_posts) ? data.hot_posts : [])
  const interactions = data?.interactions?.items || (Array.isArray(data?.interactions) ? data.interactions : [])

  return (
    <div className="space-y-6 animate-in fade-in duration-500">
      
      {/* 1. New X Posts */}
      <div className="bg-[#1e293b] border border-[#334155] rounded-xl p-5 border-t-2 border-t-blue-500 shadow-xl">
        <div className="flex justify-between items-center mb-4">
          <h3 className="font-bold text-lg text-white flex items-center">
            <MessageSquare className="w-5 h-5 mr-2 text-blue-400" /> New X Posts
          </h3>
          {recentMeta && (
            <span className="text-[10px] text-slate-500 font-mono bg-[#0f172a] px-2 py-1 rounded border border-[#334155]">
              Interval: {formatRange(recentMeta)}
            </span>
          )}
        </div>
        <div className="space-y-3 max-h-[600px] overflow-y-auto scrollbar-thin pr-2">
           {recentPosts.length > 0 ? (
             recentPosts.map((p: any, i: number) => (
               <div key={i} className="bg-[#0f172a]/40 p-3 rounded-lg border border-[#334155]/60 hover:border-blue-500/30 transition-all">
                 <div className="flex justify-between items-center mb-2">
                   <span className="text-blue-400 font-bold text-sm">{p.kol || 'KOL'}</span>
                   <div className="flex flex-col text-right">
                     <span className="text-[9px] text-slate-500 uppercase tracking-tighter">
                       Posted: {new Date(p.posted_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                     </span>
                     <span className="text-[9px] text-slate-400 uppercase tracking-tighter font-semibold">
                       Scraped: {new Date(p.captured_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                     </span>
                   </div>
                 </div>
                 <p className="text-sm text-slate-300 italic mb-3">"{truncate(p.content, 200)}"</p>
                 <div className="flex justify-between items-center">
                   <div className="flex gap-3 text-[10px] font-mono text-slate-500">
                     <span title="Views">👀 {p.views?.toLocaleString() || 0}</span>
                     <span title="Likes">👍 {p.likes?.toLocaleString() || 0}</span>
                     <span title="Reposts">🔄 {p.reposts?.toLocaleString() || 0}</span>
                     <span title="Replies">💬 {p.comments?.toLocaleString() || 0}</span>
                   </div>
                   <a href={p.post_url} target="_blank" className="text-[10px] bg-[#1e293b] hover:bg-[#334155] text-slate-400 px-2 py-1 rounded transition-colors flex items-center gap-1 border border-[#334155]">
                     View <ExternalLink className="w-3 h-3" />
                   </a>
                 </div>
               </div>
             ))
           ) : (
             <div className="text-center py-12 px-4 bg-[#0f172a]/20 rounded-xl border border-dashed border-[#334155]">
               <p className="text-sm text-slate-500 italic mb-1">No new posts found</p>
               <p className="text-[10px] text-slate-600 font-mono italic">{formatRange(recentMeta)}</p>
             </div>
           )}
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* 2. Hot Posts (Heatmap) */}
        <div className="bg-[#1e293b] border border-[#334155] rounded-xl p-5 border-t-2 border-t-orange-500 shadow-xl">
          <h3 className="font-bold text-lg mb-4 text-white flex items-center">
            <Flame className="w-5 h-5 mr-2 text-orange-400" /> Hot Posts (Heatmap)
          </h3>
          <div className="space-y-3 max-h-[400px] overflow-y-auto scrollbar-thin pr-2">
            {hotPosts.length === 0 ? (
              <p className="text-xs text-slate-500 italic p-4">No significant surges in last sync.</p>
            ) : (
              hotPosts.map((h: any, i: number) => (
                <div key={i} className="bg-[#0f172a]/50 p-3 rounded-lg border border-[#334155]">
                  <div className="flex justify-between items-center mb-1">
                    <span className="text-orange-400 font-bold text-sm">🔥 {h.kol}</span>
                    <span className="text-[10px] bg-emerald-500/20 text-emerald-400 px-1.5 py-0.5 rounded uppercase font-bold tracking-wider">
                      +{h.score} Score
                    </span>
                  </div>
                  <p className="text-xs text-slate-400 mb-2 font-medium">"{truncate(h.content, 120)}"</p>
                  <div className="flex flex-wrap gap-2 text-[10px] font-bold">
                    {h.d_views > 0 && <span className="bg-[#1e293b] text-slate-300 px-2 py-1 rounded border border-[#334155]">+{h.d_views.toLocaleString()} views</span>}
                    {h.d_likes > 0 && <span className="bg-[#1e293b] text-slate-300 px-2 py-1 rounded border border-[#334155]">+{h.d_likes.toLocaleString()} likes</span>}
                    {h.d_reposts > 0 && <span className="bg-[#1e293b] text-slate-300 px-2 py-1 rounded border border-[#334155]">+{h.d_reposts.toLocaleString()} reposts</span>}
                  </div>
                </div>
              ))
            )}
          </div>
        </div>

        {/* 3. Interaction Changes */}
        <div className="bg-[#1e293b] border border-[#334155] rounded-xl p-5 border-t-2 border-t-purple-500 shadow-xl">
          <h3 className="font-bold text-lg mb-4 text-white flex items-center">
            <Zap className="w-5 h-5 mr-2 text-purple-400" /> Post Interactions
          </h3>
          <div className="space-y-3 max-h-[400px] overflow-y-auto scrollbar-thin pr-2">
            {interactions.length === 0 ? (
              <p className="text-xs text-slate-500 italic p-4">No interaction changes in last sync.</p>
            ) : (
              interactions.map((i: any, idx: number) => (
                <div key={idx} className="bg-[#0f172a]/50 p-3 rounded-lg border border-[#334155]">
                  <div className="flex justify-between items-center mb-1">
                    <span className="text-purple-400 font-bold text-sm">⚡ {i.kol}</span>
                    <span className="text-[9px] text-slate-500 uppercase font-bold tracking-tighter">
                      {new Date(i.captured_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                    </span>
                  </div>
                  <p className="text-xs text-slate-400 mb-2 italic">"{truncate(i.content, 120)}"</p>
                  <div className="flex gap-2">
                     <span className="text-[10px] font-bold text-emerald-400">+{((i.like_delta || 0) + (i.repost_delta || 0) + (i.comment_delta || 0)).toLocaleString()} total</span>
                     <span className="text-[10px] text-slate-600">→</span>
                     <span className="text-[10px] text-blue-400 font-bold uppercase">{i.target_name || 'Activity'}</span>
                  </div>
                </div>
              ))
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
