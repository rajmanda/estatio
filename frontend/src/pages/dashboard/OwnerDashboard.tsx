import { useQuery } from '@tanstack/react-query'
import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts'
import { motion } from 'framer-motion'
import {
  BuildingOfficeIcon, CurrencyDollarIcon, ExclamationCircleIcon, WrenchScrewdriverIcon,
} from '@heroicons/react/24/outline'
import { StatCard } from '../../components/ui/StatCard'
import { GlassCard } from '../../components/ui/GlassCard'
import { GlassBadge } from '../../components/ui/GlassBadge'
import { useAuthStore } from '../../store/authStore'
import { ownersApi } from '../../services/api'
import { format } from 'date-fns'

export default function OwnerDashboard() {
  const { user } = useAuthStore()

  const { data: dashboard, isLoading } = useQuery({
    queryKey: ['owner-dashboard', user?.id],
    queryFn: () => ownersApi.getDashboard(user!.id).then(r => r.data),
    enabled: !!user?.id,
  })

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="w-8 h-8 border-2 border-indigo-500 border-t-transparent rounded-full animate-spin" />
      </div>
    )
  }

  const kpis = dashboard?.kpis ?? {}
  const alerts = dashboard?.alerts ?? []
  const properties = dashboard?.properties ?? []
  const recentInvoices = dashboard?.recent_invoices ?? []
  const recentWorkOrders = dashboard?.recent_work_orders ?? []
  const incomeData = dashboard?.income_trend ?? []

  return (
    <div className="space-y-6">
      {/* Welcome */}
      <motion.div initial={{ opacity: 0, y: -8 }} animate={{ opacity: 1, y: 0 }}>
        <h2 className="text-2xl font-bold text-white">
          Good {getGreeting()}, {user?.full_name?.split(' ')[0]} 👋
        </h2>
        <p className="text-white/50 text-sm mt-1">Here's your portfolio overview</p>
      </motion.div>

      {/* KPI row */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard title="Properties" value={kpis.total_properties ?? 0} icon={<BuildingOfficeIcon className="w-6 h-6" />} color="indigo" change={0} />
        <StatCard title="Monthly Income" value={kpis.monthly_income ?? 0} icon={<CurrencyDollarIcon className="w-6 h-6" />} color="green" prefix="$" change={kpis.income_change} changeLabel="vs last month" />
        <StatCard title="Outstanding Balance" value={kpis.outstanding_balance ?? 0} icon={<ExclamationCircleIcon className="w-6 h-6" />} color="amber" prefix="$" />
        <StatCard title="Open Work Orders" value={kpis.open_work_orders ?? 0} icon={<WrenchScrewdriverIcon className="w-6 h-6" />} color="purple" />
      </div>

      {/* Income trend chart */}
      <GlassCard>
        <h3 className="text-base font-semibold text-white mb-4">Income Trend (12 months)</h3>
        <ResponsiveContainer width="100%" height={220}>
          <AreaChart data={incomeData}>
            <defs>
              <linearGradient id="income" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="#6366f1" stopOpacity={0.4} />
                <stop offset="95%" stopColor="#6366f1" stopOpacity={0} />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
            <XAxis dataKey="month" tick={{ fill: 'rgba(255,255,255,0.4)', fontSize: 12 }} axisLine={false} tickLine={false} />
            <YAxis tick={{ fill: 'rgba(255,255,255,0.4)', fontSize: 12 }} axisLine={false} tickLine={false} tickFormatter={v => `$${(v/1000).toFixed(0)}k`} />
            <Tooltip contentStyle={{ background: 'rgba(15,12,41,0.9)', border: '1px solid rgba(255,255,255,0.1)', borderRadius: 12, color: '#fff' }} formatter={(v: number) => [`$${v.toLocaleString()}`, 'Income']} />
            <Area type="monotone" dataKey="amount" stroke="#6366f1" strokeWidth={2} fill="url(#income)" />
          </AreaChart>
        </ResponsiveContainer>
      </GlassCard>

      <div className="grid lg:grid-cols-2 gap-6">
        {/* Properties */}
        <GlassCard>
          <h3 className="text-base font-semibold text-white mb-4">Your Properties</h3>
          <div className="space-y-3">
            {properties.slice(0, 5).map((p: any) => (
              <div key={p.property_id} className="flex items-center justify-between p-3 rounded-xl bg-white/5 border border-white/8 hover:bg-white/8 transition-colors cursor-pointer">
                <div>
                  <p className="text-sm font-medium text-white">{p.name}</p>
                  <p className="text-xs text-white/40">{p.address} · {p.ownership_percentage}% ownership</p>
                </div>
                <div className="text-right">
                  <p className="text-sm font-semibold text-emerald-400">${p.monthly_income?.toLocaleString()}</p>
                  <p className="text-xs text-white/40">/ mo</p>
                </div>
              </div>
            ))}
          </div>
        </GlassCard>

        {/* Alerts */}
        <GlassCard>
          <h3 className="text-base font-semibold text-white mb-4">Alerts</h3>
          {alerts.length === 0 ? (
            <p className="text-white/30 text-sm text-center py-6">No active alerts</p>
          ) : (
            <div className="space-y-2">
              {alerts.map((alert: any, i: number) => (
                <div key={i} className="flex items-start gap-3 p-3 rounded-xl bg-white/5 border border-white/8">
                  <span className={`w-2 h-2 rounded-full mt-1.5 flex-shrink-0 ${alert.severity === 'high' ? 'bg-red-400' : 'bg-amber-400'}`} />
                  <div>
                    <p className="text-sm text-white">{alert.message}</p>
                    <p className="text-xs text-white/40 mt-0.5">{alert.type}</p>
                  </div>
                </div>
              ))}
            </div>
          )}
        </GlassCard>
      </div>

      <div className="grid lg:grid-cols-2 gap-6">
        {/* Recent Invoices */}
        <GlassCard>
          <h3 className="text-base font-semibold text-white mb-4">Recent Invoices</h3>
          <div className="space-y-2">
            {recentInvoices.slice(0, 5).map((inv: any) => (
              <div key={inv.id} className="flex items-center justify-between p-3 rounded-xl bg-white/5">
                <div>
                  <p className="text-sm font-medium text-white">{inv.invoice_number}</p>
                  <p className="text-xs text-white/40">{inv.billing_period_start} — Due {inv.due_date}</p>
                </div>
                <div className="flex items-center gap-3">
                  <span className="text-sm font-semibold text-white">${inv.total_amount?.toLocaleString()}</span>
                  <GlassBadge status={inv.status} />
                </div>
              </div>
            ))}
          </div>
        </GlassCard>

        {/* Recent Work Orders */}
        <GlassCard>
          <h3 className="text-base font-semibold text-white mb-4">Recent Work Orders</h3>
          <div className="space-y-2">
            {recentWorkOrders.slice(0, 5).map((wo: any) => (
              <div key={wo.id} className="flex items-center justify-between p-3 rounded-xl bg-white/5">
                <div>
                  <p className="text-sm font-medium text-white">{wo.title}</p>
                  <p className="text-xs text-white/40">{wo.category} · {wo.work_order_number}</p>
                </div>
                <GlassBadge status={wo.priority} />
              </div>
            ))}
          </div>
        </GlassCard>
      </div>
    </div>
  )
}

function getGreeting() {
  const h = new Date().getHours()
  if (h < 12) return 'morning'
  if (h < 17) return 'afternoon'
  return 'evening'
}
