'use client'

import { useState, useEffect } from 'react'
import { api } from '@/lib/api-client'
import {
  Loader2,
  Save,
  CheckCircle2,
  Clock,
  History,
  ChevronDown,
  ChevronUp,
  AlertCircle
} from 'lucide-react'

const WEEKDAYS = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
const HOURS = Array.from({ length: 24 }, (_, i) => i)
const MINUTES = Array.from({ length: 60 }, (_, i) => i)
const SECONDS = Array.from({ length: 60 }, (_, i) => i)

interface KolDMConfig {
  kol_id: number
  name: string
  twitter_url: string
  dm_text: string
  dm_day: string   // comma-separated: "Tuesday,Sunday"
  dm_time: string  // HH:MM:SS
}

interface DMLog {
  id: number
  kol_name: string
  content: string
  status: string
  sent_at: string
}

function parseTime(time: string): { h: string; m: string; s: string } {
  const parts = (time || '').split(':')
  return {
    h: parts[0] || '',
    m: parts[1] || '',
    s: parts[2] || '',
  }
}

function buildTime(h: string, m: string, s: string): string {
  if (h === '' && m === '' && s === '') return ''
  return `${h.padStart(2, '0')}:${m.padStart(2, '0')}:${s.padStart(2, '0')}`
}

// Returns true if all 3 DM fields are filled, or all 3 are empty
function isValid(k: KolDMConfig): boolean {
  const hasText = k.dm_text.trim() !== ''
  const hasDay = k.dm_day.trim() !== ''
  const hasTime = k.dm_time.trim() !== ''
  return (hasText && hasDay && hasTime) || (!hasText && !hasDay && !hasTime)
}

function isFullyFilled(k: KolDMConfig): boolean {
  return k.dm_text.trim() !== '' && k.dm_day.trim() !== '' && k.dm_time.trim() !== ''
}

export default function DMScheduler() {
  const [kols, setKols] = useState<KolDMConfig[]>([])
  const [savedActiveIds, setSavedActiveIds] = useState<Set<number>>(new Set())
  const [logs, setLogs] = useState<DMLog[]>([])
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [validationError, setValidationError] = useState<string | null>(null)
  const [showLogs, setShowLogs] = useState(false)

  useEffect(() => {
    fetchData()
  }, [])

  const fetchData = async () => {
    try {
      const [kolsRes, logsRes] = await Promise.all([
        api.getKOLs(),
        api.getDMLogs()
      ])
      const loaded: KolDMConfig[] = (kolsRes.kols || []).map((k: any) => ({
        kol_id: k.id,
        name: k.name,
        twitter_url: k.twitter_url || '',
        dm_text: k.dm_text || '',
        dm_day: k.dm_day || '',
        dm_time: k.dm_time || '',
      }))
      setKols(loaded)
      // Mark as active if all fields are filled on load (previously saved)
      setSavedActiveIds(new Set(
        loaded.filter(isFullyFilled).map(k => k.kol_id)
      ))
      setLogs(logsRes.logs || [])
    } catch (err) {
      console.error('Failed to fetch DM data', err)
    } finally {
      setLoading(false)
    }
  }

  const updateKol = (index: number, field: keyof KolDMConfig, value: string) => {
    setKols(prev => {
      const updated = [...prev]
      updated[index] = { ...updated[index], [field]: value }
      return updated
    })
    setSaved(false)
    setValidationError(null)
  }

  const toggleDay = (index: number, day: string) => {
    const kol = kols[index]
    const currentDays = kol.dm_day ? kol.dm_day.split(',').filter(Boolean) : []
    const newDays = currentDays.includes(day)
      ? currentDays.filter(d => d !== day)
      : [...currentDays, day]
    updateKol(index, 'dm_day', newDays.join(','))
  }

  const handleSave = async () => {
    // Validate: each KOL must be all-filled or all-empty
    const invalid = kols.filter(k => !isValid(k))
    if (invalid.length > 0) {
      setValidationError(
        `Incomplete schedule for: ${invalid.map(k => k.name).join(', ')}. Each KOL must have all three fields filled or all left empty.`
      )
      return
    }

    setSaving(true)
    setSaved(false)
    setValidationError(null)
    try {
      const schedules = kols.map(k => ({
        kol_id: k.kol_id,
        dm_text: k.dm_text.trim() || null,
        dm_day: k.dm_day.trim() || null,
        dm_time: k.dm_time.trim() || null,
      }))
      await api.saveDMSchedules(schedules)
      // Update active badges based on saved state
      setSavedActiveIds(new Set(kols.filter(isFullyFilled).map(k => k.kol_id)))
      setSaved(true)
      setTimeout(() => setSaved(false), 3000)
    } catch (err) {
      console.error('Failed to save DM schedules', err)
      alert('Failed to save. Check console for details.')
    } finally {
      setSaving(false)
    }
  }

  if (loading) {
    return (
      <div className="flex justify-center py-20">
        <Loader2 className="w-8 h-8 text-blue-500 animate-spin" />
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <div className="bg-[#1e293b] border border-[#334155] rounded-xl p-6 shadow-xl">
        <div className="flex items-center justify-between mb-4">
          <div>
            <h3 className="font-bold text-white flex items-center gap-2">
              <Clock className="w-4 h-4 text-blue-400" /> Scheduled Messages
            </h3>
            <p className="text-xs text-slate-500 mt-1">
              Fill in message, days, and time for a KOL — or leave all three empty to disable. Save to apply.
            </p>
          </div>
          <button
            onClick={handleSave}
            disabled={saving}
            className={`px-5 py-2.5 rounded-xl text-sm font-bold transition-all flex items-center gap-2 ${
              saved
                ? 'bg-emerald-600 text-white'
                : 'bg-blue-600 hover:bg-blue-500 text-white shadow-[0_10px_20px_-10px_rgba(37,99,235,0.4)]'
            } disabled:opacity-50 active:scale-[0.98]`}
          >
            {saving ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : saved ? (
              <CheckCircle2 className="w-4 h-4" />
            ) : (
              <Save className="w-4 h-4" />
            )}
            {saving ? 'Saving...' : saved ? 'Saved' : 'Save Changes'}
          </button>
        </div>

        {validationError && (
          <div className="flex items-start gap-2 bg-red-500/10 border border-red-500/30 text-red-400 text-xs rounded-xl px-4 py-3 mb-4">
            <AlertCircle className="w-4 h-4 mt-0.5 shrink-0" />
            {validationError}
          </div>
        )}

        <div className="space-y-4 max-h-[600px] overflow-y-auto scrollbar-thin pr-2">
          {kols.map((kol, i) => {
            const isActive = savedActiveIds.has(kol.kol_id)
            const isPartial = !isValid(kol)
            const { h, m, s } = parseTime(kol.dm_time)

            return (
              <div
                key={kol.kol_id}
                className={`rounded-xl border p-4 transition-all ${
                  isActive
                    ? 'bg-[#0f172a]/60 border-blue-500/40'
                    : isPartial
                    ? 'bg-[#0f172a]/40 border-amber-500/30'
                    : 'bg-[#0f172a]/30 border-[#334155]/60'
                }`}
              >
                {/* KOL Header */}
                <div className="flex items-center gap-3 mb-3">
                  <span className={`font-bold text-sm ${isActive ? 'text-blue-400' : 'text-slate-400'}`}>
                    {kol.name}
                  </span>
                  <span className="text-[10px] text-slate-600 font-mono">
                    @{kol.twitter_url.split('/').pop() || kol.name}
                  </span>
                  {isActive && (
                    <span className="text-[9px] bg-blue-500/20 text-blue-400 px-2 py-0.5 rounded-full font-bold uppercase tracking-wider">
                      Active
                    </span>
                  )}
                  {isPartial && (
                    <span className="text-[9px] bg-amber-500/20 text-amber-400 px-2 py-0.5 rounded-full font-bold uppercase tracking-wider">
                      Incomplete
                    </span>
                  )}
                </div>

                {/* Message */}
                <div className="mb-3">
                  <label className="text-[10px] font-bold text-slate-500 uppercase tracking-widest ml-1 mb-1 block">
                    Message
                  </label>
                  <textarea
                    value={kol.dm_text}
                    onChange={e => updateKol(i, 'dm_text', e.target.value)}
                    placeholder="Enter the DM message to send..."
                    rows={3}
                    className="w-full bg-slate-950/50 border border-slate-800 rounded-xl px-4 py-3 text-sm text-slate-200 placeholder-slate-700 focus:outline-none focus:ring-2 focus:ring-blue-500/40 focus:border-blue-500/50 transition-all resize-none font-medium"
                  />
                </div>

                <div className="flex flex-col lg:flex-row gap-4">
                  {/* Weekday Selection */}
                  <div className="flex-1">
                    <label className="text-[10px] font-bold text-slate-500 uppercase tracking-widest ml-1 mb-1.5 block">
                      Days
                    </label>
                    <div className="flex flex-wrap gap-1.5">
                      {WEEKDAYS.map(day => {
                        const selected = kol.dm_day.split(',').includes(day)
                        return (
                          <button
                            key={day}
                            type="button"
                            onClick={() => toggleDay(i, day)}
                            className={`px-2.5 py-1.5 rounded-lg text-[11px] font-bold transition-all ${
                              selected
                                ? 'bg-blue-600 text-white shadow-sm'
                                : 'bg-slate-950/50 text-slate-500 border border-slate-800 hover:border-slate-600'
                            }`}
                          >
                            {day.slice(0, 3)}
                          </button>
                        )
                      })}
                    </div>
                  </div>

                  {/* Time Dropdowns */}
                  <div className="w-full lg:w-auto">
                    <label className="text-[10px] font-bold text-slate-500 uppercase tracking-widest ml-1 mb-1.5 block">
                      Time
                    </label>
                    <div className="flex items-center gap-1.5">
                      {/* Hour */}
                      <select
                        value={h}
                        onChange={e => updateKol(i, 'dm_time', buildTime(e.target.value, m, s))}
                        className="bg-slate-950/50 border border-slate-800 rounded-lg px-2 py-2 text-sm text-slate-200 focus:outline-none focus:ring-2 focus:ring-blue-500/40 font-mono [color-scheme:dark] w-16"
                      >
                        <option value="">HH</option>
                        {HOURS.map(n => (
                          <option key={n} value={String(n).padStart(2, '0')}>
                            {String(n).padStart(2, '0')}
                          </option>
                        ))}
                      </select>
                      <span className="text-slate-500 font-bold">:</span>
                      {/* Minute */}
                      <select
                        value={m}
                        onChange={e => updateKol(i, 'dm_time', buildTime(h, e.target.value, s))}
                        className="bg-slate-950/50 border border-slate-800 rounded-lg px-2 py-2 text-sm text-slate-200 focus:outline-none focus:ring-2 focus:ring-blue-500/40 font-mono [color-scheme:dark] w-16"
                      >
                        <option value="">MM</option>
                        {MINUTES.map(n => (
                          <option key={n} value={String(n).padStart(2, '0')}>
                            {String(n).padStart(2, '0')}
                          </option>
                        ))}
                      </select>
                      <span className="text-slate-500 font-bold">:</span>
                      {/* Second */}
                      <select
                        value={s}
                        onChange={e => updateKol(i, 'dm_time', buildTime(h, m, e.target.value))}
                        className="bg-slate-950/50 border border-slate-800 rounded-lg px-2 py-2 text-sm text-slate-200 focus:outline-none focus:ring-2 focus:ring-blue-500/40 font-mono [color-scheme:dark] w-16"
                      >
                        <option value="">SS</option>
                        {SECONDS.map(n => (
                          <option key={n} value={String(n).padStart(2, '0')}>
                            {String(n).padStart(2, '0')}
                          </option>
                        ))}
                      </select>
                    </div>
                  </div>
                </div>
              </div>
            )
          })}

          {kols.length === 0 && (
            <div className="text-center py-12 bg-[#0f172a]/20 rounded-xl border border-dashed border-[#334155]">
              <p className="text-sm text-slate-500 italic">No KOLs found. Add KOLs in the KOLs tab first.</p>
            </div>
          )}
        </div>
      </div>

      {/* DM Send History */}
      <div className="bg-[#1e293b] border border-[#334155] rounded-xl shadow-xl">
        <button
          onClick={() => setShowLogs(!showLogs)}
          className="w-full p-5 flex items-center justify-between text-left"
        >
          <h3 className="font-bold text-white flex items-center gap-2">
            <History className="w-4 h-4 text-purple-400" /> DM Send History
            <span className="text-[10px] text-slate-500 font-normal ml-1">({logs.length} entries)</span>
          </h3>
          {showLogs ? (
            <ChevronUp className="w-4 h-4 text-slate-500" />
          ) : (
            <ChevronDown className="w-4 h-4 text-slate-500" />
          )}
        </button>

        {showLogs && (
          <div className="px-5 pb-5">
            <div className="space-y-2 max-h-[400px] overflow-y-auto scrollbar-thin pr-2">
              {logs.length === 0 ? (
                <p className="text-xs text-slate-500 italic py-4 text-center">No DMs sent yet.</p>
              ) : (
                logs.map((log) => (
                  <div key={log.id} className="bg-[#0f172a]/50 p-3 rounded-lg border border-[#334155]/60 flex items-start gap-3">
                    <span className={`text-[10px] font-bold px-2 py-0.5 rounded mt-0.5 shrink-0 ${
                      log.status === 'sent'
                        ? 'bg-emerald-500/20 text-emerald-400'
                        : 'bg-red-500/20 text-red-400'
                    }`}>
                      {log.status}
                    </span>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 mb-1">
                        <span className="text-sm font-bold text-slate-300">{log.kol_name}</span>
                        <span className="text-[10px] text-slate-600 font-mono">
                          {log.sent_at ? new Date(log.sent_at).toLocaleString([], {
                            month: 'short', day: 'numeric',
                            hour: '2-digit', minute: '2-digit'
                          }) : ''}
                        </span>
                      </div>
                      <p className="text-xs text-slate-500 truncate">{log.content}</p>
                    </div>
                  </div>
                ))
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
