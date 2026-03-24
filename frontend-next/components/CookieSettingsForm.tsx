'use client'

import { useState } from 'react'
import { api } from '@/lib/api-client'
import { Key, Save, Loader2, CheckCircle2 } from 'lucide-react'

export default function CookieSettingsForm() {
  const [loading, setLoading] = useState(false)
  const [success, setSuccess] = useState(false)
  const [formData, setFormData] = useState({
    auth_token: '',
    ct0: ''
  })

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setLoading(true)
    setSuccess(false)
    try {
      await api.saveCookies(formData)
      setSuccess(true)
      setFormData({ auth_token: '', ct0: '' })
    } catch (err) {
      console.error('Failed to save cookies', err)
      alert('Failed to save credentials. Please check your network.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <div className="flex items-center gap-2 mb-2">
         <span className={`text-[10px] px-2 py-0.5 rounded border font-bold uppercase tracking-wider ${success ? 'bg-emerald-500/10 text-emerald-500 border-emerald-500/20' : 'bg-slate-700/50 text-slate-500 border-slate-700/50'}`}>
            Status: {success ? 'Updated' : 'Not Saved'}
         </span>
      </div>
      
      <p className="text-xs text-slate-500 mb-4 italic leading-relaxed">
        Refresh your X account in a browser and copy tokens from Cookies (DevTools → Application → Cookies).
      </p>

      <div className="space-y-4">
        <div>
          <label className="text-[10px] text-slate-500 uppercase font-bold mb-1.5 block tracking-widest">auth_token</label>
          <input 
            type="password" 
            placeholder="Enter auth_token" 
            value={formData.auth_token}
            onChange={(e) => setFormData(prev => ({ ...prev, auth_token: e.target.value }))}
            required
            className="w-full bg-[#0f172a] border border-[#334155] rounded-xl px-4 py-2.5 text-sm text-white focus:border-blue-500 focus:outline-none transition-all"
          />
        </div>
        <div>
          <label className="text-[10px] text-slate-500 uppercase font-bold mb-1.5 block tracking-widest">ct0 (CSRF Token)</label>
          <input 
            type="password" 
            placeholder="Enter ct0" 
            value={formData.ct0}
            onChange={(e) => setFormData(prev => ({ ...prev, ct0: e.target.value }))}
            required
            className="w-full bg-[#0f172a] border border-[#334155] rounded-xl px-4 py-2.5 text-sm text-white focus:border-blue-500 focus:outline-none transition-all"
          />
        </div>
        
        <button 
          type="submit" 
          disabled={loading}
          className="w-full bg-blue-600 hover:bg-blue-700 text-white rounded-xl py-2.5 text-sm font-bold transition flex items-center justify-center gap-2 shadow-lg shadow-blue-500/20 disabled:opacity-50"
        >
          {loading ? (
            <Loader2 className="w-4 h-4 animate-spin" />
          ) : success ? (
            <CheckCircle2 className="w-4 h-4" />
          ) : (
            <Save className="w-4 h-4" />
          )}
          {loading ? 'Saving...' : success ? 'Credentials Updated' : 'Update X Credentials'}
        </button>
      </div>
    </form>
  )
}
