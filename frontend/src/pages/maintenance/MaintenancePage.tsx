import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { motion } from 'framer-motion'
import { PlusIcon, WrenchScrewdriverIcon } from '@heroicons/react/24/outline'
import { GlassCard } from '../../components/ui/GlassCard'
import { GlassButton } from '../../components/ui/GlassButton'
import { GlassBadge } from '../../components/ui/GlassBadge'
import { maintenanceApi } from '../../services/api'

const STATUS_TABS = ['all', 'submitted', 'in_progress', 'awaiting_approval', 'completed']
const PRIORITY_COLOR: Record<string, string> = { emergency: 'text-red-400', high: 'text-amber-400', medium: 'text-indigo-400', low: 'text-white/40' }

export default function MaintenancePage() {
  const [statusFilter, setStatusFilter] = useState('all')
  const [priorityFilter, setPriorityFilter] = useState('')
  const qc = useQueryClient()

  const { data, isLoading } = useQuery({
    queryKey: ['work-orders', statusFilter, priorityFilter],
    queryFn: () => maintenanceApi.list({
      status: statusFilter !== 'all' ? statusFilter : undefined,
      priority: priorityFilter || undefined,
      limit: 50,
    }).then(r => r.data),
  })

  const { data: summary } = useQuery({
    queryKey: ['maintenance-summary'],
    queryFn: () => maintenanceApi.getSummary().then(r => r.data),
  })

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-bold text-white">Maintenance</h2>
          <p className="text-white/40 text-sm mt-0.5">{data?.total ?? 0} work orders</p>
        </div>
        <GlassButton variant="primary" icon={<PlusIcon className="w-4 h-4" />}>New Work Order</GlassButton>
      </div>

      {/* Summary cards */}
      {summary && (
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
          {[
            { label: 'Open', value: summary.open, color: 'text-amber-400' },
            { label: 'In Progress', value: summary.in_progress, color: 'text-indigo-400' },
            { label: 'Emergency', value: summary.emergency, color: 'text-red-400' },
            { label: 'Completed (30d)', value: summary.completed_30d, color: 'text-emerald-400' },
          ].map(s => (
            <GlassCard key={s.label} className="text-center">
              <p className={`text-2xl font-bold ${s.color}`}>{s.value ?? 0}</p>
              <p className="text-white/40 text-xs mt-1">{s.label}</p>
            </GlassCard>
          ))}
        </div>
      )}

      {/* Status filter tabs */}
      <div className="flex gap-2 overflow-x-auto pb-1">
        {STATUS_TABS.map(tab => (
          <button
            key={tab}
            onClick={() => setStatusFilter(tab)}
            className={`px-3 py-1.5 rounded-lg text-sm font-medium whitespace-nowrap transition-all ${
              statusFilter === tab
                ? 'bg-indigo-600/40 border border-indigo-500/40 text-white'
                : 'text-white/50 hover:text-white hover:bg-white/8'
            }`}
          >
            {tab === 'all' ? 'All' : tab.replace('_', ' ').replace(/\b\w/g, c => c.toUpperCase())}
          </button>
        ))}
        <select
          value={priorityFilter}
          onChange={e => setPriorityFilter(e.target.value)}
          className="ml-auto bg-white/8 border border-white/15 rounded-lg px-2 py-1 text-sm text-white focus:outline-none"
        >
          <option value="">All Priority</option>
          <option value="emergency">Emergency</option>
          <option value="high">High</option>
          <option value="medium">Medium</option>
          <option value="low">Low</option>
        </select>
      </div>

      {/* Work Orders */}
      {isLoading ? (
        <div className="flex items-center justify-center h-48">
          <div className="w-8 h-8 border-2 border-indigo-500 border-t-transparent rounded-full animate-spin" />
        </div>
      ) : (
        <div className="space-y-3">
          {(data?.work_orders ?? []).map((wo: any, i: number) => (
            <motion.div key={wo.id} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.03 }}>
              <GlassCard hover>
                <div className="flex items-start justify-between gap-4">
                  <div className="flex items-start gap-3 flex-1 min-w-0">
                    <div className="p-2 rounded-lg bg-white/5 border border-white/10 flex-shrink-0">
                      <WrenchScrewdriverIcon className="w-4 h-4 text-white/60" />
                    </div>
                    <div className="min-w-0">
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className="text-xs text-white/30 font-mono">{wo.work_order_number}</span>
                        <span className={`text-xs font-semibold uppercase ${PRIORITY_COLOR[wo.priority] ?? 'text-white/40'}`}>{wo.priority}</span>
                      </div>
                      <p className="font-medium text-white mt-0.5">{wo.title}</p>
                      <p className="text-sm text-white/50 mt-1 truncate">{wo.description}</p>
                      <p className="text-xs text-white/30 mt-1 capitalize">{wo.category}</p>
                    </div>
                  </div>
                  <div className="flex flex-col items-end gap-2 flex-shrink-0">
                    <GlassBadge status={wo.status} />
                    {wo.approved_amount && (
                      <span className="text-sm font-semibold text-white">${wo.approved_amount.toLocaleString()}</span>
                    )}
                  </div>
                </div>
              </GlassCard>
            </motion.div>
          ))}
        </div>
      )}

      {data?.total === 0 && !isLoading && (
        <div className="text-center py-16 text-white/30">
          <WrenchScrewdriverIcon className="w-12 h-12 mx-auto mb-3 opacity-30" />
          <p>No work orders found</p>
        </div>
      )}
    </div>
  )
}
