'use client'

import { useState, useEffect } from 'react'
import { api } from '@/lib/api-client'
import { Loader2, CheckCircle2, Lock } from 'lucide-react'

export default function DMPasscodeForm() {
  const [passcode, setPasscode] = useState('')
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [hasExisting, setHasExisting] = useState(false)

  useEffect(() => {
    api.getSettings().then((s: any) => {
      if (s.has_dm_passcode) setHasExisting(true)
    }).catch(() => {})
  }, [])

  const handleSave = async () => {
    if (!passcode.trim()) return
    setSaving(true)
    setSaved(false)
    try {
      await api.saveDMPasscode(passcode.trim())
      setSaved(true)
      setHasExisting(true)
      setPasscode('')
      setTimeout(() => setSaved(false), 3000)
    } catch (err) {
      console.error('Failed to save DM passcode', err)
      alert('Failed to save DM passcode.')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2 mb-2">
        <span className={`text-[10px] px-2 py-0.5 rounded border font-bold uppercase tracking-wider ${
          hasExisting
            ? 'bg-emerald-500/10 text-emerald-500 border-emerald-500/20'
            : 'bg-amber-500/10 text-amber-500 border-amber-500/20'
        }`}>
          {hasExisting ? 'Passcode Set' : 'Not Set'}
        </span>
      </div>

      <p className="text-xs text-slate-500 italic leading-relaxed">
        X/Twitter requires an encrypted DM passcode to access messages.
        Enter your 4-digit passcode so the DM scheduler can send messages on your behalf.
      </p>

      <div>
        <label className="text-[10px] text-slate-500 uppercase font-bold mb-1.5 block tracking-widest">
          DM Passcode
        </label>
        <input
          type="password"
          placeholder={hasExisting ? '****' : 'Enter your X DM passcode'}
          value={passcode}
          onChange={e => { setPasscode(e.target.value); setSaved(false) }}
          maxLength={20}
          className="w-full bg-[#0f172a] border border-[#334155] rounded-xl px-4 py-2.5 text-sm text-white focus:border-blue-500 focus:outline-none transition-all"
        />
      </div>

      <button
        onClick={handleSave}
        disabled={saving || !passcode.trim()}
        className={`w-full py-3 rounded-xl text-sm font-bold transition-all flex items-center justify-center gap-2 active:scale-[0.98] ${
          saved
            ? 'bg-emerald-600 text-white'
            : 'bg-blue-600 hover:bg-blue-500 text-white shadow-[0_10px_20px_-10px_rgba(37,99,235,0.4)]'
        } disabled:opacity-50`}
      >
        {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : saved ? <CheckCircle2 className="w-4 h-4" /> : <Lock className="w-4 h-4" />}
        {saving ? 'Saving...' : saved ? 'Saved' : hasExisting ? 'Update Passcode' : 'Save Passcode'}
      </button>
    </div>
  )
}
