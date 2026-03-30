import { useQuery } from '@tanstack/react-query'
import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  PieChart, Pie, Cell, Legend,
} from 'recharts'
import { BuildingOfficeIcon, UsersIcon, CurrencyDollarIcon, WrenchScrewdriverIcon, ExclamationTriangleIcon } from '@heroicons/react/24/outline'
import { StatCard } from '../../components/ui/StatCard'
import { GlassCard } from '../../components/ui/GlassCard'
import { GlassBadge } from '../../components/ui/GlassBadge'
import { propertiesApi, ownersApi, maintenanceApi } from '../../services/api'

const PIE_COLORS = ['#6366f1', '#a855f7', '#f59e0b', '#10b981', '#ef4444', '#64748b']

export default function AdminDashboard() {
  const { data: properties } = useQuery({ queryKey: ['properties-summary'], queryFn: () => propertiesApi.list({ limit: 5 }).then(r => r.data) })
  const { data: maintenance } = useQuery({ queryKey: ['maintenance-summary'], queryFn: () => maintenanceApi.getSummary().then(r => r.data) })

  const kpis = [
    { title: 'Total Properties', value: properties?.total ?? 0, icon: <BuildingOfficeIcon className="w-6 h-6" />, color: 'indigo' as const },
    { title: 'MTD Income',       value: 0,                      icon: <CurrencyDollarIcon className="w-6 h-6" />,  color: 'green' as const, prefix: '$' },
    { title: 'Open Work Orders', value: maintenance?.open ?? 0, icon: <WrenchScrewdriverIcon className="w-6 h-6" />, color: 'amber' as const },
    { title: 'Overdue Invoices', value: 0,                      icon: <ExclamationTriangleIcon className="w-6 h-6" />, color: 'red' as const },
  ]

  const woStatusData = Object.entries(maintenance?.by_status ?? {}).map(([name, value]) => ({ name, value }))

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-bold text-white">Admin Dashboard</h2>
        <p className="text-white/50 text-sm mt-1">Platform-wide overview</p>
      </div>

      {/* KPIs */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {kpis.map(k => (
          <StatCard key={k.title} {...k} />
        ))}
      </div>

      <div className="grid lg:grid-cols-3 gap-6">
        {/* Revenue trend */}
        <GlassCard className="lg:col-span-2">
          <h3 className="text-base font-semibold text-white mb-4">Revenue Trend</h3>
          <ResponsiveContainer width="100%" height={220}>
            <AreaChart data={[]}>
              <defs>
                <linearGradient id="rev" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#a855f7" stopOpacity={0.4} />
                  <stop offset="95%" stopColor="#a855f7" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
              <XAxis tick={{ fill: 'rgba(255,255,255,0.4)', fontSize: 12 }} axisLine={false} tickLine={false} />
              <YAxis tick={{ fill: 'rgba(255,255,255,0.4)', fontSize: 12 }} axisLine={false} tickLine={false} />
              <Tooltip contentStyle={{ background: 'rgba(15,12,41,0.9)', border: '1px solid rgba(255,255,255,0.1)', borderRadius: 12, color: '#fff' }} />
              <Area type="monotone" dataKey="amount" stroke="#a855f7" strokeWidth={2} fill="url(#rev)" />
            </AreaChart>
          </ResponsiveContainer>
        </GlassCard>

        {/* WO Status pie */}
        <GlassCard>
          <h3 className="text-base font-semibold text-white mb-4">Work Order Status</h3>
          {woStatusData.length > 0 ? (
            <ResponsiveContainer width="100%" height={220}>
              <PieChart>
                <Pie data={woStatusData} cx="50%" cy="50%" innerRadius={50} outerRadius={80} paddingAngle={3} dataKey="value">
                  {woStatusData.map((_, i) => <Cell key={i} fill={PIE_COLORS[i % PIE_COLORS.length]} />)}
                </Pie>
                <Legend wrapperStyle={{ color: 'rgba(255,255,255,0.6)', fontSize: 11 }} />
                <Tooltip contentStyle={{ background: 'rgba(15,12,41,0.9)', border: '1px solid rgba(255,255,255,0.1)', borderRadius: 12 }} />
              </PieChart>
            </ResponsiveContainer>
          ) : (
            <div className="flex items-center justify-center h-[220px] text-white/30 text-sm">No data</div>
          )}
        </GlassCard>
      </div>

      {/* Recent properties */}
      <GlassCard>
        <h3 className="text-base font-semibold text-white mb-4">Recent Properties</h3>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-white/10">
                <th className="text-left py-2 px-3 text-white/40 font-medium">Property</th>
                <th className="text-left py-2 px-3 text-white/40 font-medium">Type</th>
                <th className="text-left py-2 px-3 text-white/40 font-medium">Status</th>
                <th className="text-right py-2 px-3 text-white/40 font-medium">Monthly Rent</th>
              </tr>
            </thead>
            <tbody>
              {(properties?.properties ?? []).map((p: any) => (
                <tr key={p.id} className="border-b border-white/5 hover:bg-white/3 transition-colors">
                  <td className="py-2.5 px-3 text-white font-medium">{p.name}</td>
                  <td className="py-2.5 px-3 text-white/60 capitalize">{p.property_type?.replace('_', ' ')}</td>
                  <td className="py-2.5 px-3"><GlassBadge status={p.status} /></td>
                  <td className="py-2.5 px-3 text-right text-emerald-400 font-semibold">
                    {p.monthly_rent ? `$${p.monthly_rent.toLocaleString()}` : '—'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </GlassCard>
    </div>
  )
}
