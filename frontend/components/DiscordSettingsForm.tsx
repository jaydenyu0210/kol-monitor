'use client'

import { useState, useEffect } from 'react'
import { api } from '@/lib/api-client'
import { 
  Bell, 
  Save,
  Loader2,
  CheckCircle2
} from 'lucide-react'

interface WebhookConfigs {
  discord_webhook_posts: string
  discord_webhook_interactions: string
  discord_webhook_heatmap: string
  discord_webhook_following: string
  discord_webhook_followers: string
  scrape_interval_mins: number
}

export default function DiscordSettingsForm() {
  const [configs, setConfigs] = useState<WebhookConfigs>({
    discord_webhook_posts: '',
    discord_webhook_interactions: '',
    discord_webhook_heatmap: '',
    discord_webhook_following: '',
    discord_webhook_followers: '',
    scrape_interval_mins: 30
  })
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)

  useEffect(() => {
    const fetchConfigs = async () => {
      try {
        const data = await api.getSettings()
        setConfigs({
          discord_webhook_posts: data.discord_webhook_posts || '',
          discord_webhook_interactions: data.discord_webhook_interactions || '',
          discord_webhook_heatmap: data.discord_webhook_heatmap || '',
          discord_webhook_following: data.discord_webhook_following || '',
          discord_webhook_followers: data.discord_webhook_followers || '',
          scrape_interval_mins: data.scrape_interval_mins || 30
        })
      } catch (err) {
        console.error('Failed to load settings', err)
      } finally {
        setLoading(false)
      }
    }
    fetchConfigs()
  }, [])

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault()
    setSaving(true)
    setSaved(false)
    try {
      await api.saveWebhooks(configs)
      setSaved(true)
      setTimeout(() => setSaved(false), 3000)
    } catch (err) {
      alert('Failed to save settings')
    } finally {
      setSaving(false)
    }
  }

  if (loading) {
    return (
      <div className="h-64 flex items-center justify-center">
        <Loader2 className="w-8 h-8 text-blue-500 animate-spin" />
      </div>
    )
  }

  return (
    <form onSubmit={handleSave} className="space-y-4 animate-in fade-in duration-500">
      <div className="space-y-4">
        <WebhookInput
          label="New Posts Webhook"
          value={configs.discord_webhook_posts}
          onChange={(val) => setConfigs({ ...configs, discord_webhook_posts: val })}
        />
        <WebhookInput
          label="Interactions Webhook"
          value={configs.discord_webhook_interactions}
          onChange={(val) => setConfigs({ ...configs, discord_webhook_interactions: val })}
        />
        <WebhookInput
          label="Heatmap Webhook"
          value={configs.discord_webhook_heatmap}
          onChange={(val) => setConfigs({ ...configs, discord_webhook_heatmap: val })}
        />
        <WebhookInput
          label="Following Webhook"
          value={configs.discord_webhook_following}
          onChange={(val) => setConfigs({ ...configs, discord_webhook_following: val })}
        />
      </div>

      <button
        type="submit"
        disabled={saving}
        className={`w-full flex items-center justify-center gap-2 py-2.5 rounded-xl font-bold text-sm transition-all shadow-lg ${
          saved 
            ? 'bg-emerald-600 text-white shadow-emerald-500/20' 
            : 'bg-purple-600 hover:bg-purple-700 text-white shadow-purple-500/20'
        }`}
      >
        {saving ? (
          <Loader2 className="w-4 h-4 animate-spin" />
        ) : saved ? (
          <CheckCircle2 className="w-4 h-4" />
        ) : (
          <Save className="w-4 h-4" />
        )}
        {saving ? 'Saving...' : saved ? 'Settings Saved' : 'Save Webhook Settings'}
      </button>
    </form>
  )
}

function WebhookInput({ label, value, onChange }: { 
  label: string, 
  value: string, 
  onChange: (val: string) => void
}) {
  return (
    <div className="space-y-1">
      <label className="text-[10px] text-slate-500 uppercase font-bold mb-1 block tracking-widest">
        {label}
      </label>
      <input
        type="text"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder="https://discord.com/api/webhooks/..."
        className="w-full bg-[#0f172a] border border-[#334155] rounded-xl px-4 py-2 text-xs text-white placeholder-slate-700 focus:border-purple-500 focus:outline-none transition-all font-mono"
      />
    </div>
  )
}
