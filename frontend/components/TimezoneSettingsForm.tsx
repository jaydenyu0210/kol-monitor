'use client'

import { useState, useEffect } from 'react'
import { api } from '@/lib/api-client'
import { Loader2, CheckCircle2, Globe } from 'lucide-react'

// Common IANA timezones grouped by region
const TIMEZONE_OPTIONS = [
  { label: 'UTC', value: 'UTC' },
  // Americas
  { label: 'US/Eastern (UTC-5/-4)', value: 'America/New_York' },
  { label: 'US/Central (UTC-6/-5)', value: 'America/Chicago' },
  { label: 'US/Mountain (UTC-7/-6)', value: 'America/Denver' },
  { label: 'US/Pacific (UTC-8/-7)', value: 'America/Los_Angeles' },
  { label: 'US/Alaska (UTC-9/-8)', value: 'America/Anchorage' },
  { label: 'US/Hawaii (UTC-10)', value: 'Pacific/Honolulu' },
  { label: 'Canada/Toronto (UTC-5/-4)', value: 'America/Toronto' },
  { label: 'Canada/Vancouver (UTC-8/-7)', value: 'America/Vancouver' },
  { label: 'Brazil/São Paulo (UTC-3)', value: 'America/Sao_Paulo' },
  { label: 'Argentina/Buenos Aires (UTC-3)', value: 'America/Argentina/Buenos_Aires' },
  { label: 'Mexico/Mexico City (UTC-6/-5)', value: 'America/Mexico_City' },
  // Europe
  { label: 'UK/London (UTC+0/+1)', value: 'Europe/London' },
  { label: 'France/Paris (UTC+1/+2)', value: 'Europe/Paris' },
  { label: 'Germany/Berlin (UTC+1/+2)', value: 'Europe/Berlin' },
  { label: 'Netherlands/Amsterdam (UTC+1/+2)', value: 'Europe/Amsterdam' },
  { label: 'Spain/Madrid (UTC+1/+2)', value: 'Europe/Madrid' },
  { label: 'Italy/Rome (UTC+1/+2)', value: 'Europe/Rome' },
  { label: 'Sweden/Stockholm (UTC+1/+2)', value: 'Europe/Stockholm' },
  { label: 'Finland/Helsinki (UTC+2/+3)', value: 'Europe/Helsinki' },
  { label: 'Greece/Athens (UTC+2/+3)', value: 'Europe/Athens' },
  { label: 'Russia/Moscow (UTC+3)', value: 'Europe/Moscow' },
  // Asia & Pacific
  { label: 'UAE/Dubai (UTC+4)', value: 'Asia/Dubai' },
  { label: 'India/Kolkata (UTC+5:30)', value: 'Asia/Kolkata' },
  { label: 'Bangladesh/Dhaka (UTC+6)', value: 'Asia/Dhaka' },
  { label: 'Thailand/Bangkok (UTC+7)', value: 'Asia/Bangkok' },
  { label: 'China/Shanghai (UTC+8)', value: 'Asia/Shanghai' },
  { label: 'Singapore (UTC+8)', value: 'Asia/Singapore' },
  { label: 'Hong Kong (UTC+8)', value: 'Asia/Hong_Kong' },
  { label: 'Taiwan/Taipei (UTC+8)', value: 'Asia/Taipei' },
  { label: 'Philippines/Manila (UTC+8)', value: 'Asia/Manila' },
  { label: 'Japan/Tokyo (UTC+9)', value: 'Asia/Tokyo' },
  { label: 'Korea/Seoul (UTC+9)', value: 'Asia/Seoul' },
  { label: 'Australia/Sydney (UTC+10/+11)', value: 'Australia/Sydney' },
  { label: 'Australia/Melbourne (UTC+10/+11)', value: 'Australia/Melbourne' },
  { label: 'Australia/Brisbane (UTC+10)', value: 'Australia/Brisbane' },
  { label: 'Australia/Perth (UTC+8)', value: 'Australia/Perth' },
  { label: 'New Zealand/Auckland (UTC+12/+13)', value: 'Pacific/Auckland' },
]

export default function TimezoneSettingsForm() {
  // Initialize immediately from browser — no waiting for API
  const [timezone, setTimezone] = useState<string>(
    () => Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC'
  )
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [localTime, setLocalTime] = useState('')

  useEffect(() => {
    // Override with saved timezone if the user has one; otherwise keep browser-detected
    api.getSettings().then((s: any) => {
      if (s.timezone) {
        setTimezone(s.timezone)
      }
    }).catch(() => {})
  }, [])

  useEffect(() => {
    // Show current local time in selected timezone
    const update = () => {
      try {
        const t = new Intl.DateTimeFormat('en-US', {
          timeZone: timezone,
          weekday: 'long',
          hour: '2-digit',
          minute: '2-digit',
          second: '2-digit',
          hour12: false
        }).format(new Date())
        setLocalTime(t)
      } catch {
        setLocalTime('')
      }
    }
    update()
    const interval = setInterval(update, 1000)
    return () => clearInterval(interval)
  }, [timezone])

  const handleSave = async () => {
    setSaving(true)
    setSaved(false)
    try {
      await api.saveTimezone(timezone)
      setSaved(true)
      setTimeout(() => setSaved(false), 3000)
    } catch (err) {
      console.error('Failed to save timezone', err)
      alert('Failed to save timezone.')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="space-y-4">
      <div>
        <label className="text-[10px] font-bold text-slate-500 uppercase tracking-widest ml-1 mb-1.5 block">
          Your Timezone
        </label>
        <select
          value={timezone}
          onChange={e => { setTimezone(e.target.value); setSaved(false) }}
          className="w-full bg-slate-950/50 border border-slate-800 rounded-xl px-4 py-3 text-sm text-slate-200 focus:outline-none focus:ring-2 focus:ring-blue-500/40 focus:border-blue-500/50 transition-all [color-scheme:dark]"
        >
          {/* If browser timezone isn't in the preset list, show it at the top */}
          {!TIMEZONE_OPTIONS.find(o => o.value === timezone) && (
            <option value={timezone}>{timezone} (auto-detected)</option>
          )}
          {TIMEZONE_OPTIONS.map(opt => (
            <option key={opt.value} value={opt.value}>{opt.label}</option>
          ))}
        </select>
      </div>

      {localTime && (
        <p className="text-[11px] text-slate-500 font-mono ml-1">
          Current local time: <span className="text-blue-400 font-bold">{localTime}</span>
        </p>
      )}

      <button
        onClick={handleSave}
        disabled={saving}
        className={`w-full py-3 rounded-xl text-sm font-bold transition-all flex items-center justify-center gap-2 active:scale-[0.98] ${
          saved
            ? 'bg-emerald-600 text-white'
            : 'bg-blue-600 hover:bg-blue-500 text-white shadow-[0_10px_20px_-10px_rgba(37,99,235,0.4)]'
        } disabled:opacity-50`}
      >
        {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : saved ? <CheckCircle2 className="w-4 h-4" /> : <Globe className="w-4 h-4" />}
        {saving ? 'Saving...' : saved ? 'Saved' : 'Save Timezone'}
      </button>
    </div>
  )
}
