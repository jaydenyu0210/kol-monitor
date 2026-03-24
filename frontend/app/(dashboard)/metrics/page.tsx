import EngagementChart from '@/components/EngagementChart'
import { TrendingUp, Activity } from 'lucide-react'

export default async function MetricsPage() {
  // Dummy Chart Data for Demonstration
  const chartData = {
    labels: ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'],
    datasets: [
      {
        label: 'Engagement Score',
        data: [420, 580, 490, 720, 680, 850, 910],
        borderColor: '#3b82f6',
        backgroundColor: 'rgba(59, 130, 246, 0.1)',
        tension: 0.4,
        fill: true,
      },
    ],
  }

  return (
    <div className="space-y-8 animate-in fade-in duration-500">
      <div className="flex items-center justify-between mb-2">
        <h2 className="text-xl font-bold text-white flex items-center gap-2">
          <Activity className="w-5 h-5 text-blue-400" />
          Network Metrics & Trends
        </h2>
        <div className="text-xs text-slate-500 font-medium">Historical engagement analysis</div>
      </div>

      <div className="grid grid-cols-1 gap-8">
        <div className="bg-[#1e293b] border border-[#334155] rounded-xl p-8 shadow-xl">
          <div className="mb-8">
             <h3 className="text-lg font-bold text-white mb-1 flex items-center gap-2">
               <TrendingUp className="w-4 h-4 text-emerald-400" />
               Aggregated Engagement
             </h3>
             <p className="text-xs text-slate-500 font-medium italic">Tracking total likes, reposts, and comments across all monitored KOLs</p>
          </div>
          
          <div className="h-[400px]">
             <EngagementChart data={chartData} />
          </div>
        </div>
      </div>

      <div className="mt-8 p-6 bg-slate-900/50 rounded-xl border border-dashed border-[#334155] flex flex-col items-center justify-center text-center gap-3">
         <div className="w-12 h-12 bg-[#1e293b] rounded-full flex items-center justify-center border border-[#334155]">
            <TrendingUp className="w-6 h-6 text-slate-600" />
         </div>
         <p className="text-sm text-slate-500 font-medium italic">
           Advanced predictive metrics and AI-driven growth analysis are currently being calculated.
           <br /> Check back after the next full scrape cycle for updated insights.
         </p>
      </div>
    </div>
  )
}
