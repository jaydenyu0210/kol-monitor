'use client'

import { useState } from 'react'
import AddKOLForm from '@/components/AddKOLForm'
import KOLOverviewTable from '@/components/KOLOverviewTable'
import { Users, Plus } from 'lucide-react'

export default function KOLManagementPage() {
  const [refreshKey, setRefreshKey] = useState(0)
  const [showAddForm, setShowAddForm] = useState(false)

  const handleRefresh = () => {
    setRefreshKey(prev => prev + 1)
    setShowAddForm(false)
  }

  return (
    <div className="space-y-8 animate-in fade-in duration-500">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-xl font-bold text-white flex items-center gap-2">
           <Users className="w-5 h-5 text-blue-400" />
           Manage My KOLs
        </h2>
        <button 
          onClick={() => setShowAddForm(!showAddForm)}
          className="bg-emerald-600 hover:bg-emerald-700 text-white px-4 py-2 rounded-lg text-xs font-bold transition flex items-center gap-2"
        >
          <Plus className={`w-3.5 h-3.5 transition-transform ${showAddForm ? 'rotate-45' : ''}`} />
          {showAddForm ? 'Cancel' : 'Add New KOL'}
        </button>
      </div>

      <div className="grid grid-cols-1 gap-8">
        {showAddForm && (
          <div className="bg-[#1e293b] border border-[#334155] rounded-xl p-8 shadow-xl animate-in zoom-in-95 duration-200">
             <AddKOLForm onSuccess={handleRefresh} />
          </div>
        )}
        
        <div className="bg-[#1e293b] border border-[#334155] rounded-xl p-8 shadow-xl" key={refreshKey}>
          <KOLOverviewTable />
        </div>
      </div>
    </div>
  )
}
