import { redirect } from 'next/navigation'
import { createClient } from '@/lib/supabase/server'
import { LogOut } from 'lucide-react'
import Link from 'next/link'
import DashboardNav from '@/components/DashboardNav'
import ScrapeTimer from '@/components/ScrapeTimer'

export default async function DashboardLayout({
  children,
}: {
  children: React.ReactNode
}) {
  const supabase = await createClient()
  const { data: { user } } = await supabase.auth.getUser()

  if (!user) {
    redirect('/login')
  }

  return (
    <div className="min-h-screen bg-[#0f172a] text-[#e2e8f0] font-inter">
      <div className="max-w-7xl mx-auto px-4 py-6">
        {/* Header */}
        <div className="flex items-center justify-between mb-8">
          <div>
            <h1 className="text-2xl font-bold text-white flex items-center gap-3">
              <span className="text-3xl">📡</span> KOL Monitor Dashboard
            </h1>
            <p className="text-sm text-slate-400 mt-1 uppercase tracking-widest font-medium opacity-80">
              LinkedIn & Twitter KOL Tracking System
            </p>
          </div>

          <div className="flex items-center gap-6">
            <ScrapeTimer />
            
            <div className="flex items-center gap-4">
              <div className="text-right hidden sm:block">
                <p className="text-[10px] text-slate-500 font-bold uppercase tracking-widest">Logged in safe</p>
                <p className="text-xs font-bold text-blue-400">{user.email}</p>
              </div>
              
              <form action="/auth/signout" method="post">
                <button className="p-2.5 bg-[#1e293b] hover:bg-red-500/10 text-slate-500 hover:text-red-400 rounded-xl border border-[#334155] transition-all">
                  <LogOut className="w-5 h-5" />
                </button>
              </form>
            </div>
          </div>
        </div>

        {/* Navigation Tabs */}
        <DashboardNav />

        {/* Main Content */}
        <main className="bg-[#1e293b] border border-[#334155] rounded-xl p-6 shadow-xl min-h-[500px] scrollbar-thin">
          {children}
        </main>

        {/* Footer */}
        <div className="mt-8 flex justify-center opacity-20">
          <div className="flex items-center gap-2">
            <div className="w-8 h-[1px] bg-slate-400"></div>
            <span className="text-[10px] font-bold text-slate-400 uppercase tracking-[0.3em]">KOL Monitor Pro</span>
            <div className="w-8 h-[1px] bg-slate-400"></div>
          </div>
        </div>
      </div>
    </div>
  )
}
