import { 
  Users, 
  MessageSquare, 
  TrendingUp,
  Share2
} from 'lucide-react'

interface StatCardsProps {
  stats: {
    total_kols: number
    posts_today: number
    interactions_today: number
    connection_changes_today: number
    total_posts: number
  }
}

export default function StatCards({ stats }: StatCardsProps) {
  return (
    <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-8">
      <StatCard 
        label="TOTAL KOLs" 
        value={stats.total_kols.toString()} 
        subValue="Active"
        subColor="text-emerald-400"
      />
      <StatCard 
        label="POSTS TODAY" 
        value={stats.posts_today.toString()} 
        subValue={`total: ${stats.total_posts}`}
        subColor="text-slate-500"
      />
      <StatCard 
        label="INTERACTIONS TODAY" 
        value={stats.interactions_today.toLocaleString()} 
        subValue="comments & likes"
        subColor="text-blue-400"
      />
      <StatCard 
        label="CONNECTION CHANGES" 
        value={stats.connection_changes_today.toString()} 
        subValue="follow/unfollow"
        subColor="text-amber-400"
      />
    </div>
  )
}

function StatCard({ label, value, subValue, subColor }: { label: string, value: string, subValue: string, subColor: string }) {
  return (
    <div className="bg-[#1e293b] border border-[#334155] rounded-xl p-4 transition-all hover:translate-y-[-2px] cursor-pointer shadow-lg shadow-black/20 group">
      <div className="text-slate-400 text-[10px] font-bold uppercase tracking-widest mb-1">{label}</div>
      <div className="text-2xl font-bold text-white mb-1 tracking-tight">{value}</div>
      <div className={`text-[10px] font-semibold flex items-center gap-1 ${subColor}`}>
        {subValue.startsWith('total') ? '' : '● '}
        {subValue}
      </div>
    </div>
  )
}
