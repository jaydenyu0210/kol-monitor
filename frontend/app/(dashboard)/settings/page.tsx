import DiscordSettingsForm from '@/components/DiscordSettingsForm'
import CookieSettingsForm from '@/components/CookieSettingsForm'
import TimezoneSettingsForm from '@/components/TimezoneSettingsForm'
import DMPasscodeForm from '@/components/DMPasscodeForm'
import {
  Bell,
  Key,
  Lock,
  Settings,
  Globe
} from 'lucide-react'

export default function SettingsPage() {
  return (
    <div className="space-y-8 animate-in fade-in duration-500">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-xl font-bold text-white flex items-center gap-2">
           <Settings className="w-5 h-5 text-blue-400" />
           SaaS System Settings
        </h2>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
        <div className="space-y-8">
           {/* Twitter Credentials */}
           <div className="bg-[#1e293b] border border-[#334155] rounded-xl p-6 shadow-xl border-l-4 border-l-blue-500">
             <h3 className="font-bold text-white mb-4 flex items-center gap-2">
                <Key className="w-4 h-4 text-blue-400" />
                My Twitter / X Credentials
             </h3>
             <CookieSettingsForm />
           </div>

           {/* System Information */}
           <div className="bg-[#1e293b] border border-[#334155] rounded-xl p-6 shadow-xl border-l-4 border-l-slate-500">
              <h3 className="font-bold text-slate-400 mb-2 flex items-center gap-2 text-sm uppercase tracking-widest">
                System Status
              </h3>
              <div className="space-y-2 mt-4">
                 <div className="flex justify-between text-xs">
                    <span className="text-slate-500 font-bold uppercase">Backend API</span>
                    <span className="text-emerald-400 font-bold">Connected (Railway)</span>
                 </div>
                 <div className="flex justify-between text-xs">
                    <span className="text-slate-500 font-bold uppercase">Auth Provider</span>
                    <span className="text-blue-400 font-bold">Supabase SSR</span>
                 </div>
              </div>
           </div>
        </div>

        <div className="space-y-8">
           {/* Timezone */}
           <div className="bg-[#1e293b] border border-[#334155] rounded-xl p-6 shadow-xl border-l-4 border-l-blue-400">
             <h3 className="font-bold text-white mb-1 flex items-center gap-2">
               <Globe className="w-4 h-4 text-blue-400" />
               Timezone
             </h3>
             <p className="text-xs text-slate-500 mb-4 italic">Used for DM scheduling. Set to your local timezone.</p>
             <TimezoneSettingsForm />
           </div>

           {/* DM Passcode */}
           <div className="bg-[#1e293b] border border-[#334155] rounded-xl p-6 shadow-xl border-l-4 border-l-amber-500">
             <h3 className="font-bold text-white mb-1 flex items-center gap-2">
               <Lock className="w-4 h-4 text-amber-400" />
               X DM Passcode
             </h3>
             <p className="text-xs text-slate-500 mb-4 italic">Required for the DM scheduler to send messages.</p>
             <DMPasscodeForm />
           </div>

           {/* Discord Notifications */}
           <div className="bg-[#1e293b] border border-[#334155] rounded-xl p-6 shadow-xl border-l-4 border-l-purple-500">
             <h3 className="font-bold text-white mb-4 flex items-center gap-2">
                <Bell className="w-4 h-4 text-purple-400" />
                My Discord Notifications
             </h3>
             <p className="text-xs text-slate-500 mb-6 italic">Paste your Discord channel webhooks below to receive alerts.</p>
             <DiscordSettingsForm />
           </div>
        </div>
      </div>
    </div>
  )
}
