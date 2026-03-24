'use client'

import { useState, useEffect } from 'react'
import { api } from '@/lib/api-client'
import { 
  Users, 
  Trash2, 
  ExternalLink, 
  Clock, 
  AlertCircle,
  Loader2,
  CheckCircle2
} from 'lucide-react'

export default function KOLList({ refreshKey }: { refreshKey: number }) {
  const [kols, setKols] = useState<any[]>([])
  const [loading, setLoading] = useState(true)
  const [deleting, setDeleting] = useState<number | null>(null)

  const fetchKols = async () => {
    try {
      const data = await api.getKOLs()
      setKols(data.kols || [])
    } catch (err) {
      console.error('Failed to fetch KOLs', err)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchKols()
  }, [refreshKey])

  const handleDelete = async (id: number) => {
    if (!confirm('Are you sure you want to stop monitoring this profile?')) return
    
    setDeleting(id)
    try {
      await api.deleteKOL(id)
      setKols(kols.filter(k => k.id !== id))
    } catch (err) {
      alert('Failed to delete KOL')
    } finally {
      setDeleting(null)
    }
  }

  if (loading) {
    return (
      <div className="h-64 bg-slate-900/40 rounded-3xl flex items-center justify-center border border-white/5 shadow-xl">
        <Loader2 className="w-8 h-8 text-blue-500 animate-spin" />
      </div>
    )
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between px-2 mb-2">
         <div className="flex items-center gap-2 text-slate-500 text-[10px] font-bold uppercase tracking-widest">
           <Users className="w-3.5 h-3.5" />
           Active Monitoring Jobs ({kols.length})
         </div>
      </div>

      <div className="grid grid-cols-1 gap-3">
        {kols.length > 0 ? (
          kols.map((kol) => (
            <div 
              key={kol.id} 
              className="group bg-slate-900/40 hover:bg-slate-900/80 border border-white/5 hover:border-blue-500/20 rounded-2xl p-4 transition-all flex items-center justify-between gap-4"
            >
              <div className="flex items-center gap-4 min-w-0">
                <div className="w-12 h-12 rounded-2xl bg-slate-950 border border-white/5 flex items-center justify-center text-blue-400 font-bold group-hover:bg-blue-600/10 group-hover:border-blue-600/20 transition-all">
                  {kol.name.charAt(0)}
                </div>
                <div className="min-w-0">
                  <div className="flex items-center gap-2 mb-0.5">
                    <h4 className="text-sm font-bold text-white truncate">{kol.name}</h4>
                    {kol.status === 'active' ? (
                      <CheckCircle2 className="w-3 h-3 text-emerald-500" />
                    ) : (
                      <AlertCircle className="w-3 h-3 text-slate-600" />
                    )}
                  </div>
                  <div className="flex items-center gap-3">
                    <a 
                      href={kol.twitter_url} 
                      target="_blank" 
                      rel="noopener noreferrer"
                      className="text-[10px] text-slate-500 hover:text-blue-400 transition-colors flex items-center gap-1 font-medium truncate max-w-[150px]"
                    >
                      {kol.twitter_url.replace('https://x.com/', '@').replace('https://twitter.com/', '@')}
                      <ExternalLink className="w-2.5 h-2.5" />
                    </a>
                    <span className="text-[10px] text-slate-700 flex items-center gap-1 font-medium">
                      <Clock className="w-2.5 h-2.5" />
                      {kol.last_scraped_at ? new Date(kol.last_scraped_at).toLocaleDateString() : 'Never scraped'}
                    </span>
                  </div>
                </div>
              </div>

              <div className="flex items-center gap-2 opacity-0 group-hover:opacity-100 transition-opacity">
                <button 
                  onClick={() => handleDelete(kol.id)}
                  disabled={deleting === kol.id}
                  className="p-2.5 bg-red-500/10 hover:bg-red-500/20 text-red-400 rounded-xl border border-red-500/20 transition-all active:scale-95 disabled:opacity-50"
                  title="Remove Profile"
                >
                  {deleting === kol.id ? <Loader2 className="w-4 h-4 animate-spin" /> : <Trash2 className="w-4 h-4" />}
                </button>
              </div>
            </div>
          ))
        ) : (
          <div className="text-center py-20 bg-slate-900/20 rounded-3xl border border-dashed border-white/5">
             <div className="flex justify-center mb-4">
               <div className="p-4 bg-slate-950 rounded-full border border-white/5">
                 <Users className="w-10 h-10 text-slate-800" />
               </div>
             </div>
             <p className="text-slate-600 font-medium">No profiles added yet</p>
          </div>
        )}
      </div>
    </div>
  )
}
