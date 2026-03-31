'use client'

import DMScheduler from '@/components/DMScheduler'
import { Mail } from 'lucide-react'

export default function DMSchedulerPage() {
  return (
    <div className="space-y-8 animate-in fade-in duration-500">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-xl font-bold text-white flex items-center gap-2">
          <Mail className="w-5 h-5 text-blue-400" />
          DM Scheduler
        </h2>
      </div>
      <DMScheduler />
    </div>
  )
}
