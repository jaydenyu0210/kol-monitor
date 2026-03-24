'use client'

import { useState, useEffect } from 'react'
import { api } from '@/lib/api-client'
import { ExternalLink, Trash2, Search, Loader2 } from 'lucide-react'

export default function KOLOverviewTable() {
  const [kols, setKols] = useState<any[]>([])
  const [loading, setLoading] = useState(true)
  const [search, setSearch] = useState('')

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
  }, [])

  const filteredKols = kols.filter(k => 
    k.name.toLowerCase().includes(search.toLowerCase()) ||
    (k.org && k.org.toLowerCase().includes(search.toLowerCase()))
  )

  const getCategoryBadge = (cat: string) => {
    if (!cat) return null
    const c = cat.toLowerCase()
    let cls = 'bg-blue-500/10 text-blue-400 border-blue-500/20'
    if (c.includes('vc') || c.includes('venture')) cls = 'bg-amber-500/10 text-amber-500 border-amber-500/20'
    else if (c.includes('ai')) cls = 'bg-purple-500/10 text-purple-400 border-purple-500/20'
    else if (c.includes('product')) cls = 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20'
    
    return (
      <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold uppercase border ${cls}`}>
        {cat}
      </span>
    )
  }

  if (loading) {
    return (
      <div className="text-center py-20 text-slate-500 flex flex-col items-center gap-4">
        <Loader2 className="w-8 h-8 animate-spin text-blue-500" />
        <p className="text-sm font-medium animate-pulse">Loading KOL data...</p>
      </div>
    )
  }

  return (
    <div className="space-y-6 animate-in fade-in duration-500">
      <div className="flex flex-col sm:flex-row items-center justify-between gap-4">
        <h2 className="text-lg font-bold text-white flex items-center gap-2">
          KOL Overview <span className="text-slate-500 text-sm font-medium">({filteredKols.length})</span>
        </h2>
        <div className="relative group w-full sm:w-64">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-slate-500 group-focus-within:text-blue-400 transition-colors" />
          <input 
            type="text" 
            placeholder="Search KOLs..." 
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full bg-[#0f172a] border border-[#334155] rounded-lg pl-9 pr-3 py-1.5 text-sm text-white focus:border-blue-500 focus:outline-none transition-all placeholder:text-slate-700"
          />
        </div>
      </div>

      <div className="overflow-x-auto scrollbar-thin">
        <table className="w-full text-sm border-collapse">
          <thead>
            <tr className="text-left text-slate-400 text-[10px] font-bold uppercase tracking-wider border-b border-[#334155]">
              <th className="pb-4 pr-4">Name</th>
              <th className="pb-4 pr-4">Organization</th>
              <th className="pb-4 pr-4">Category</th>
              <th className="pb-4 pr-4 text-center">Posts</th>
              <th className="pb-4 pr-4 text-center">Interactions</th>
              <th className="pb-4 pr-4 text-center">Followers</th>
              <th className="pb-4 text-right">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-[#334155]/30">
            {filteredKols.map((k) => (
              <tr key={k.id} className="hover:bg-[#334155]/20 transition-colors group">
                <td className="py-4 pr-4">
                  <a 
                    href={k.twitter_url || k.linkedin_url || '#'} 
                    target="_blank" 
                    rel="noopener noreferrer"
                    className="text-blue-400 hover:text-blue-300 font-bold transition flex items-center gap-1.5"
                  >
                    {k.name}
                    <ExternalLink className="w-3 h-3 opacity-0 group-hover:opacity-100 transition-opacity" />
                  </a>
                </td>
                <td className="py-4 pr-4 text-slate-400 font-medium">{k.org || '-'}</td>
                <td className="py-4 pr-4">{getCategoryBadge(k.category || 'X KOL')}</td>
                <td className="py-4 pr-4 text-center font-mono text-slate-400">{k.post_count || 0}</td>
                <td className="py-4 pr-4 text-center font-mono text-slate-400">{k.interaction_count || 0}</td>
                <td className="py-4 pr-4 text-center font-mono text-slate-400">
                  {k.latest_followers ? k.latest_followers.toLocaleString() : '-'}
                </td>
                <td className="py-4 text-right">
                   <button 
                     onClick={async () => {
                       if (confirm(`Remove ${k.name} from monitoring?`)) {
                         try {
                           await api.deleteKOL(k.id)
                           fetchKols()
                         } catch (err) {
                           alert('Failed to delete KOL')
                         }
                       }
                     }}
                     className="text-red-500/50 hover:text-red-400 p-2 rounded-lg hover:bg-red-500/5 transition-all opacity-0 group-hover:opacity-100"
                   >
                      <Trash2 className="w-4 h-4" />
                   </button>
                </td>
              </tr>
            ))}
            {filteredKols.length === 0 && (
              <tr>
                <td colSpan={7} className="py-20 text-center text-slate-600 italic">
                  No KOLs found matching your search.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}
