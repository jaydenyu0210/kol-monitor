'use client'

import { useState, useEffect } from 'react'
import { api } from '@/lib/api-client'
import { 
  MessageSquare, 
  TrendingUp, 
  Clock, 
  ExternalLink,
  Loader2,
  Trash2
} from 'lucide-react'

export default function InteractionFeed() {
  const [feed, setFeed] = useState<any>(null)
  const [loading, setLoading] = useState(true)

  const fetchFeed = async () => {
    try {
      const data = await api.getOverviewFeed()
      setFeed(data)
    } catch (err) {
      console.error('Failed to fetch feed', err)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchFeed()
    const interval = setInterval(fetchFeed, 10000)
    return () => clearInterval(interval)
  }, [])

  if (loading && !feed) {
    return (
      <div className="h-64 bg-[#1e293b] rounded-xl flex items-center justify-center border border-[#334155] animate-pulse">
        <Loader2 className="w-8 h-8 text-blue-500 animate-spin" />
      </div>
    )
  }

  const interactions = feed?.interactions || []

  return (
    <div className="space-y-4 animate-in fade-in duration-500">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-lg font-bold text-white flex items-center gap-2">
          Recent Interactions ({interactions.length})
        </h2>
        <div className="text-[10px] text-slate-600 font-bold uppercase tracking-widest">Auto-refreshing</div>
      </div>

      <div className="grid grid-cols-1 gap-3">
        {interactions.length > 0 ? (
          interactions.map((item: any, i: number) => (
            <div 
              key={i} 
              className="bg-[#1e293b]/50 hover:bg-[#1e293b] border border-[#334155]/50 hover:border-[#334155] rounded-xl p-4 transition-all"
            >
              <div className="flex items-center justify-between mb-3">
                <div className="flex items-center gap-2">
                   <span className="font-bold text-blue-400 text-sm">{item.kol_name || 'Anonymous User'}</span>
                   <span className="text-slate-500 text-xs text-slate-600">Captured:</span>
                   <span className="text-xs text-slate-500 font-medium">
                     {new Date(item.captured_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                   </span>
                </div>
                <a 
                  href={item.url} 
                  target="_blank" 
                  rel="noopener noreferrer"
                  className="p-1.5 hover:bg-slate-700/50 rounded-lg text-slate-600 hover:text-blue-400 transition-all font-bold text-[10px] flex items-center gap-1 uppercase tracking-tight"
                >
                  Source <ExternalLink className="w-3 h-3" />
                </a>
              </div>
              
              <p className="text-sm text-slate-300 leading-relaxed italic mb-4 line-clamp-2">
                "{item.content || 'Interaction detected on profile...'}"
              </p>

              <div className="flex items-center gap-6 text-[10px] font-bold uppercase tracking-widest text-[#94a3b8]">
                <div className="flex items-center gap-1.5">
                   <TrendingUp className="w-3.5 h-3.5 text-emerald-500" />
                   {item.likes || 0} Likes
                </div>
                <div className="flex items-center gap-1.5">
                   <MessageSquare className="w-3.5 h-3.5 text-blue-400" />
                   {item.comments || 0} Replies
                </div>
                <div className="flex items-center gap-1.5 ml-auto">
                   <div className="px-2 py-0.5 bg-blue-500/10 text-blue-500 rounded border border-blue-500/20">
                     Target: {item.target_name || 'Activity'}
                   </div>
                </div>
              </div>
            </div>
          ))
        ) : (
          <div className="text-center py-20 bg-slate-900/20 rounded-xl border border-dashed border-[#334155]">
            <p className="text-slate-600 font-medium italic">No interactions captured in the last 7 days.</p>
          </div>
        )}
      </div>
    </div>
  )
}
