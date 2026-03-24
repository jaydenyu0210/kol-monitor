'use client'

import { useState } from 'react'
import { api } from '@/lib/api-client'
import { Plus, UserPlus, Loader2, XCircle } from 'lucide-react'

interface AddKOLFormProps {
  onSuccess: () => void
}

export default function AddKOLForm({ onSuccess }: AddKOLFormProps) {
  const [name, setName] = useState('')
  const [url, setUrl] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setLoading(true)
    setError(null)

    try {
      await api.addKOL(name, url)
      setName('')
      setUrl('')
      onSuccess()
    } catch (err: any) {
      setError(err.message || 'Failed to add KOL')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="bg-slate-900/60 backdrop-blur-xl border border-white/5 rounded-3xl p-8 shadow-xl animate-in fade-in slide-in-from-top-4 duration-500">
      <div className="flex items-center gap-4 mb-8">
        <div className="p-3 bg-blue-500/10 rounded-2xl border border-blue-500/20 text-blue-400 shadow-[0_0_20px_rgba(59,130,246,0.15)]">
          <UserPlus className="w-6 h-6" />
        </div>
        <div>
          <h3 className="text-lg font-bold text-white mb-0.5">Add Profile</h3>
          <p className="text-xs text-slate-500 font-medium">Add a new X profile to your monitoring list</p>
        </div>
      </div>

      <form onSubmit={handleSubmit} className="space-y-6">
        {error && (
          <div className="p-4 bg-red-500/10 border border-red-500/20 rounded-2xl flex items-center gap-3 text-red-400 text-xs font-medium">
            <XCircle className="w-4 h-4" />
            {error}
          </div>
        )}

        <div className="space-y-2">
          <label className="text-[10px] font-bold text-slate-500 uppercase tracking-widest ml-1">Profile Name (Reference)</label>
          <input 
            type="text" 
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="e.g. Elon Musk"
            required
            className="w-full bg-slate-950/50 border border-slate-800 rounded-2xl px-5 py-4 text-sm text-slate-200 placeholder-slate-700 focus:outline-none focus:ring-2 focus:ring-blue-500/40 focus:border-blue-500/50 transition-all font-medium"
          />
        </div>

        <div className="space-y-2">
          <label className="text-[10px] font-bold text-slate-500 uppercase tracking-widest ml-1">X URL / Handle</label>
          <input 
            type="text" 
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            placeholder="https://x.com/username"
            required
            className="w-full bg-slate-950/50 border border-slate-800 rounded-2xl px-5 py-4 text-sm text-slate-200 placeholder-slate-700 focus:outline-none focus:ring-2 focus:ring-blue-500/40 focus:border-blue-500/50 transition-all font-medium"
          />
        </div>

        <button
          type="submit"
          disabled={loading}
          className="w-full bg-blue-600 hover:bg-blue-500 disabled:bg-blue-900/50 text-white font-bold py-4 rounded-2xl transition-all shadow-[0_10px_20px_-10px_rgba(37,99,235,0.4)] flex items-center justify-center gap-2 active:scale-[0.98]"
        >
          {loading ? <Loader2 className="w-5 h-5 animate-spin" /> : <Plus className="w-5 h-5" />}
          {loading ? 'Adding Profile...' : 'Create Monitoring Job'}
        </button>
      </form>
    </div>
  )
}
