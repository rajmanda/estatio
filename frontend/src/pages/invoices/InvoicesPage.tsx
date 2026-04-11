import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { motion } from 'framer-motion'
import {
  DocumentTextIcon, MagnifyingGlassIcon, CalendarDaysIcon,
  ExclamationTriangleIcon, CheckCircleIcon, ClockIcon,
} from '@heroicons/react/24/outline'
import { GlassCard } from '../../components/ui/GlassCard'
import { GlassBadge, type BadgeStatus } from '../../components/ui/GlassBadge'
import { api } from '../../services/api'

interface Invoice {
  id: string
  invoice_number: string
  owner_id: string
  owner_name?: string
  property_name?: string
  amount: number
  balance_due: number
  status: string
  due_date: string
  issue_date: string
  description?: string
}

function fmt(n: number) {
  return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(n)
}

function statusIcon(status: string) {
  switch (status) {
    case 'paid': return <CheckCircleIcon className="w-4 h-4 text-emerald-400" />
    case 'overdue': return <ExclamationTriangleIcon className="w-4 h-4 text-red-400" />
    case 'pending': return <ClockIcon className="w-4 h-4 text-amber-400" />
    default: return <DocumentTextIcon className="w-4 h-4 text-white/40" />
  }
}

export default function InvoicesPage() {
  const [search, setSearch] = useState('')
  const [statusFilter, setStatusFilter] = useState('')
  const [selected, setSelected] = useState<Invoice | null>(null)

  const { data, isLoading } = useQuery({
    queryKey: ['invoices', search, statusFilter],
    queryFn: () =>
      api.get('/accounting/invoices', {
        params: { search: search || undefined, status: statusFilter || undefined, limit: 50 },
      }).then(r => r.data),
  })

  const invoices: Invoice[] = data?.invoices ?? []

  const summary = {
    total: invoices.length,
    outstanding: invoices.filter(i => i.status !== 'paid').reduce((s, i) => s + i.balance_due, 0),
    overdue: invoices.filter(i => i.status === 'overdue').length,
    collected: invoices.filter(i => i.status === 'paid').reduce((s, i) => s + i.amount, 0),
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-bold text-white">Invoices</h2>
          <p className="text-white/40 text-sm mt-0.5">{data?.total ?? 0} total</p>
        </div>
      </div>

      {/* Summary cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <GlassCard>
          <p className="text-xs text-white/40 mb-1">Outstanding</p>
          <p className="text-xl font-bold text-amber-400">{fmt(summary.outstanding)}</p>
        </GlassCard>
        <GlassCard>
          <p className="text-xs text-white/40 mb-1">Overdue</p>
          <p className="text-xl font-bold text-red-400">{summary.overdue}</p>
        </GlassCard>
        <GlassCard>
          <p className="text-xs text-white/40 mb-1">Collected MTD</p>
          <p className="text-xl font-bold text-emerald-400">{fmt(summary.collected)}</p>
        </GlassCard>
        <GlassCard>
          <p className="text-xs text-white/40 mb-1">Total Invoices</p>
          <p className="text-xl font-bold text-white">{summary.total}</p>
        </GlassCard>
      </div>

      {/* Filters */}
      <GlassCard className="flex flex-wrap gap-3">
        <div className="relative flex-1 min-w-48">
          <MagnifyingGlassIcon className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-white/40" />
          <input
            value={search}
            onChange={e => setSearch(e.target.value)}
            placeholder="Search by invoice # or owner…"
            className="w-full bg-white/8 border border-white/15 rounded-xl pl-9 pr-4 py-2 text-sm text-white placeholder-white/30 focus:outline-none focus:border-indigo-500/60"
          />
        </div>
        <select
          value={statusFilter}
          onChange={e => setStatusFilter(e.target.value)}
          className="bg-white/8 border border-white/15 rounded-xl px-3 py-2 text-sm text-white focus:outline-none"
        >
          <option value="">All Statuses</option>
          <option value="draft">Draft</option>
          <option value="pending">Pending</option>
          <option value="paid">Paid</option>
          <option value="overdue">Overdue</option>
          <option value="void">Void</option>
        </select>
      </GlassCard>

      {/* Invoice list */}
      {isLoading ? (
        <div className="flex items-center justify-center h-48">
          <div className="w-8 h-8 border-2 border-indigo-500 border-t-transparent rounded-full animate-spin" />
        </div>
      ) : (
        <div className="space-y-2">
          {invoices.map((inv, i) => (
            <motion.div key={inv.id} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.03 }}>
              <GlassCard hover className="cursor-pointer" onClick={() => setSelected(selected?.id === inv.id ? null : inv)}>
                <div className="flex items-center gap-4">
                  <div className="shrink-0">{statusIcon(inv.status)}</div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-0.5">
                      <span className="font-medium text-white text-sm">{inv.invoice_number}</span>
                      <GlassBadge status={inv.status as BadgeStatus} />
                    </div>
                    <p className="text-xs text-white/40 truncate">
                      {inv.owner_name ?? inv.owner_id}
                      {inv.property_name ? ` · ${inv.property_name}` : ''}
                    </p>
                  </div>
                  <div className="text-right shrink-0">
                    <p className="font-semibold text-white text-sm">{fmt(inv.amount)}</p>
                    {inv.balance_due > 0 && inv.status !== 'paid' && (
                      <p className="text-xs text-amber-400">Due: {fmt(inv.balance_due)}</p>
                    )}
                  </div>
                  <div className="text-right shrink-0 hidden md:block">
                    <div className="flex items-center gap-1.5 text-xs text-white/40">
                      <CalendarDaysIcon className="w-3.5 h-3.5" />
                      <span>{new Date(inv.due_date).toLocaleDateString()}</span>
                    </div>
                  </div>
                </div>

                {/* Expanded detail */}
                {selected?.id === inv.id && (
                  <motion.div initial={{ height: 0, opacity: 0 }} animate={{ height: 'auto', opacity: 1 }} className="mt-4 pt-4 border-t border-white/10">
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
                      <div>
                        <p className="text-white/40 text-xs mb-1">Issue Date</p>
                        <p className="text-white">{new Date(inv.issue_date).toLocaleDateString()}</p>
                      </div>
                      <div>
                        <p className="text-white/40 text-xs mb-1">Due Date</p>
                        <p className="text-white">{new Date(inv.due_date).toLocaleDateString()}</p>
                      </div>
                      <div>
                        <p className="text-white/40 text-xs mb-1">Total</p>
                        <p className="text-white font-semibold">{fmt(inv.amount)}</p>
                      </div>
                      <div>
                        <p className="text-white/40 text-xs mb-1">Balance Due</p>
                        <p className={`font-semibold ${inv.balance_due > 0 ? 'text-amber-400' : 'text-emerald-400'}`}>{fmt(inv.balance_due)}</p>
                      </div>
                    </div>
                    {inv.description && <p className="text-white/50 text-sm mt-3">{inv.description}</p>}
                  </motion.div>
                )}
              </GlassCard>
            </motion.div>
          ))}
        </div>
      )}

      {!isLoading && invoices.length === 0 && (
        <div className="text-center py-16 text-white/30">
          <DocumentTextIcon className="w-12 h-12 mx-auto mb-3 opacity-30" />
          <p>No invoices found</p>
        </div>
      )}
    </div>
  )
}
