import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { motion } from 'framer-motion'
import {
  UsersIcon, MagnifyingGlassIcon, EnvelopeIcon,
  PhoneIcon, HomeIcon, CalendarDaysIcon,
} from '@heroicons/react/24/outline'
import { GlassCard } from '../../components/ui/GlassCard'
import { GlassBadge, type BadgeStatus } from '../../components/ui/GlassBadge'
import { api } from '../../services/api'

interface Tenant {
  id: string
  first_name: string
  last_name: string
  email: string
  phone?: string
  property_id?: string
  property_name?: string
  unit_id?: string
  lease_start_date?: string
  lease_end_date?: string
  monthly_rent?: number
  status?: string
}

function daysUntil(dateStr?: string) {
  if (!dateStr) return null
  const diff = Math.ceil((new Date(dateStr).getTime() - Date.now()) / 86400000)
  return diff
}

export default function TenantsPage() {
  const [search, setSearch] = useState('')
  const [statusFilter, setStatusFilter] = useState('')

  const { data, isLoading } = useQuery({
    queryKey: ['tenants', search, statusFilter],
    queryFn: () =>
      api.get('/tenants', { params: { search: search || undefined, status: statusFilter || undefined, limit: 50 } })
         .then(r => r.data),
  })

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-bold text-white">Tenants</h2>
          <p className="text-white/40 text-sm mt-0.5">{data?.total ?? 0} total</p>
        </div>
      </div>

      {/* Filters */}
      <GlassCard className="flex flex-wrap gap-3">
        <div className="relative flex-1 min-w-48">
          <MagnifyingGlassIcon className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-white/40" />
          <input
            value={search}
            onChange={e => setSearch(e.target.value)}
            placeholder="Search tenants…"
            className="w-full bg-white/8 border border-white/15 rounded-xl pl-9 pr-4 py-2 text-sm text-white placeholder-white/30 focus:outline-none focus:border-indigo-500/60"
          />
        </div>
        <select
          value={statusFilter}
          onChange={e => setStatusFilter(e.target.value)}
          className="bg-white/8 border border-white/15 rounded-xl px-3 py-2 text-sm text-white focus:outline-none"
        >
          <option value="">All Statuses</option>
          <option value="active">Active</option>
          <option value="pending">Pending</option>
          <option value="past">Past</option>
          <option value="eviction">Eviction</option>
        </select>
      </GlassCard>

      {/* Tenant cards */}
      {isLoading ? (
        <div className="flex items-center justify-center h-48">
          <div className="w-8 h-8 border-2 border-indigo-500 border-t-transparent rounded-full animate-spin" />
        </div>
      ) : (
        <div className="grid sm:grid-cols-2 xl:grid-cols-3 gap-4">
          {(data?.tenants ?? []).map((t: Tenant, i: number) => {
            const daysLeft = daysUntil(t.lease_end_date)
            const leaseWarning = daysLeft !== null && daysLeft <= 60 && daysLeft >= 0
            return (
              <motion.div key={t.id} initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.04 }}>
                <GlassCard hover>
                  <div className="flex items-start justify-between mb-3">
                    <div className="w-10 h-10 rounded-full bg-gradient-to-br from-emerald-500 to-teal-600 flex items-center justify-center text-white font-semibold text-sm">
                      {t.first_name?.[0]}{t.last_name?.[0]}
                    </div>
                    <GlassBadge status={(t.status ?? 'active') as BadgeStatus} />
                  </div>
                  <h3 className="font-semibold text-white">{t.first_name} {t.last_name}</h3>
                  <div className="mt-2 space-y-1.5">
                    <div className="flex items-center gap-2 text-sm text-white/50">
                      <EnvelopeIcon className="w-3.5 h-3.5 shrink-0" />
                      <span className="truncate">{t.email}</span>
                    </div>
                    {t.phone && (
                      <div className="flex items-center gap-2 text-sm text-white/50">
                        <PhoneIcon className="w-3.5 h-3.5 shrink-0" />
                        <span>{t.phone}</span>
                      </div>
                    )}
                    {t.property_name && (
                      <div className="flex items-center gap-2 text-sm text-white/50">
                        <HomeIcon className="w-3.5 h-3.5 shrink-0" />
                        <span className="truncate">{t.property_name}{t.unit_id ? ` · Unit ${t.unit_id}` : ''}</span>
                      </div>
                    )}
                    {t.lease_end_date && (
                      <div className={`flex items-center gap-2 text-sm ${leaseWarning ? 'text-amber-400' : 'text-white/50'}`}>
                        <CalendarDaysIcon className="w-3.5 h-3.5 shrink-0" />
                        <span>Lease ends {new Date(t.lease_end_date).toLocaleDateString()}</span>
                        {leaseWarning && <span className="text-xs">({daysLeft}d)</span>}
                      </div>
                    )}
                    {t.monthly_rent && (
                      <div className="text-sm font-semibold text-emerald-400">
                        ${t.monthly_rent.toLocaleString()}/mo
                      </div>
                    )}
                  </div>
                </GlassCard>
              </motion.div>
            )
          })}
        </div>
      )}

      {!isLoading && (data?.total === 0 || !data) && (
        <div className="text-center py-16 text-white/30">
          <UsersIcon className="w-12 h-12 mx-auto mb-3 opacity-30" />
          <p>No tenants found</p>
        </div>
      )}
    </div>
  )
}
