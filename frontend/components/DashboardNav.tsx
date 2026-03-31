'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'
import {
  LayoutDashboard,
  Activity,
  Hash,
  Users,
  Settings,
  MessageSquare,
  Mail
} from 'lucide-react'

export default function DashboardNav() {
  const pathname = usePathname()

  const navItems = [
    { href: '/discord', label: 'Discord', icon: <MessageSquare className="w-4 h-4" /> },
    { href: '/metrics', label: 'Metrics', icon: <Activity className="w-4 h-4" /> },
    { href: '/heatmap', label: 'Heatmap', icon: <Hash className="w-4 h-4" /> },
    { href: '/kols', label: 'KOLs', icon: <Users className="w-4 h-4" /> },
    { href: '/dm-scheduler', label: 'DM Scheduler', icon: <Mail className="w-4 h-4" /> },
    { href: '/settings', label: 'Settings', icon: <Settings className="w-4 h-4" /> },
  ]

  return (
    <div className="flex gap-2 mb-8 flex-wrap">
      {navItems.map((item) => {
        const isActive = pathname === item.href
        return (
          <Link
            key={item.href}
            href={item.href}
            className={`flex items-center gap-2 px-5 py-2.5 rounded-xl text-sm font-bold transition-all ${
              isActive 
                ? 'bg-blue-600 text-white shadow-lg shadow-blue-500/20' 
                : 'bg-[#1e293b] text-slate-400 hover:bg-[#334155] border border-[#334155]'
            }`}
          >
            {item.icon}
            {item.label}
          </Link>
        )
      })}
    </div>
  )
}
