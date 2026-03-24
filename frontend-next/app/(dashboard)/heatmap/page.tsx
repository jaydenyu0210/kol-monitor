import BubbleHeatmap from '@/components/BubbleHeatmap'

export default function HeatmapPage() {
  return (
    <div className="space-y-8 animate-in fade-in duration-500">
      <div className="bg-[#1e293b] border border-[#334155] rounded-xl p-8 shadow-xl">
        <BubbleHeatmap />
      </div>
    </div>
  )
}
