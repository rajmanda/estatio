import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell,
} from 'recharts'
import { BookOpenIcon, ScaleIcon, ArrowTrendingUpIcon, BanknotesIcon } from '@heroicons/react/24/outline'
import { GlassCard } from '../../components/ui/GlassCard'
import { GlassButton } from '../../components/ui/GlassButton'
import { accountingApi } from '../../services/api'

const TABS = ['Trial Balance', 'Income Statement', 'Balance Sheet', 'Journal Entries'] as const
type Tab = (typeof TABS)[number]

function fmt(n: number) {
  return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 }).format(n)
}

function TrialBalance() {
  const now = new Date()
  const { data, isLoading } = useQuery({
    queryKey: ['trial-balance'],
    queryFn: () => accountingApi.getTrialBalance({ year: now.getFullYear(), month: now.getMonth() + 1 }).then(r => r.data),
  })

  if (isLoading) return <div className="flex items-center justify-center h-48"><div className="w-8 h-8 border-2 border-indigo-500 border-t-transparent rounded-full animate-spin" /></div>

  const accounts: { account_name: string; account_type: string; debit_balance: number; credit_balance: number }[] = data?.accounts ?? []

  return (
    <GlassCard>
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-base font-semibold text-white">Trial Balance</h3>
        <div className="text-xs text-white/40">{now.toLocaleDateString('en-US', { month: 'long', year: 'numeric' })}</div>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-white/40 text-left border-b border-white/10">
              <th className="pb-2 font-medium">Account</th>
              <th className="pb-2 font-medium">Type</th>
              <th className="pb-2 font-medium text-right">Debit</th>
              <th className="pb-2 font-medium text-right">Credit</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-white/5">
            {accounts.map((a, i) => (
              <tr key={i} className="text-white/70 hover:text-white transition-colors">
                <td className="py-2">{a.account_name}</td>
                <td className="py-2 capitalize text-white/40 text-xs">{a.account_type}</td>
                <td className="py-2 text-right font-mono">{a.debit_balance ? fmt(a.debit_balance) : '—'}</td>
                <td className="py-2 text-right font-mono">{a.credit_balance ? fmt(a.credit_balance) : '—'}</td>
              </tr>
            ))}
          </tbody>
          {data && (
            <tfoot>
              <tr className="border-t-2 border-white/20 text-white font-semibold">
                <td colSpan={2} className="pt-3">Totals</td>
                <td className="pt-3 text-right font-mono">{fmt(data.total_debits ?? 0)}</td>
                <td className="pt-3 text-right font-mono">{fmt(data.total_credits ?? 0)}</td>
              </tr>
            </tfoot>
          )}
        </table>
        {accounts.length === 0 && (
          <div className="text-center py-8 text-white/30 text-sm">No entries this period</div>
        )}
      </div>
    </GlassCard>
  )
}

function IncomeStatement() {
  const now = new Date()
  const { data, isLoading } = useQuery({
    queryKey: ['income-statement'],
    queryFn: () => accountingApi.getIncomeStatement({ year: now.getFullYear() }).then(r => r.data),
  })

  if (isLoading) return <div className="flex items-center justify-center h-48"><div className="w-8 h-8 border-2 border-indigo-500 border-t-transparent rounded-full animate-spin" /></div>

  const revenue = data?.revenue ?? []
  const expenses = data?.expenses ?? []
  const netIncome = (data?.total_revenue ?? 0) - (data?.total_expenses ?? 0)

  const chartData = [
    { name: 'Revenue', value: data?.total_revenue ?? 0, color: '#10b981' },
    { name: 'Expenses', value: data?.total_expenses ?? 0, color: '#ef4444' },
    { name: 'Net Income', value: netIncome, color: netIncome >= 0 ? '#6366f1' : '#f59e0b' },
  ]

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-3 gap-4">
        {chartData.map(d => (
          <GlassCard key={d.name}>
            <p className="text-xs text-white/40 mb-1">{d.name}</p>
            <p className={`text-xl font-bold ${d.value < 0 ? 'text-red-400' : 'text-white'}`}>{fmt(d.value)}</p>
          </GlassCard>
        ))}
      </div>
      <GlassCard>
        <h3 className="text-base font-semibold text-white mb-4">P&L Summary — {now.getFullYear()}</h3>
        <ResponsiveContainer width="100%" height={200}>
          <BarChart data={chartData} barSize={48}>
            <XAxis dataKey="name" tick={{ fill: 'rgba(255,255,255,0.4)', fontSize: 12 }} axisLine={false} tickLine={false} />
            <YAxis tick={{ fill: 'rgba(255,255,255,0.3)', fontSize: 11 }} axisLine={false} tickLine={false} tickFormatter={v => `$${(v/1000).toFixed(0)}k`} />
            <Tooltip formatter={(v: number) => fmt(v)} contentStyle={{ background: 'rgba(15,12,41,0.9)', border: '1px solid rgba(255,255,255,0.1)', borderRadius: 12 }} labelStyle={{ color: 'white' }} itemStyle={{ color: 'rgba(255,255,255,0.7)' }} />
            <Bar dataKey="value" radius={[6, 6, 0, 0]}>
              {chartData.map((d, i) => <Cell key={i} fill={d.color} fillOpacity={0.8} />)}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </GlassCard>
      <div className="grid md:grid-cols-2 gap-4">
        <GlassCard>
          <h4 className="text-sm font-semibold text-emerald-400 mb-3">Revenue</h4>
          <div className="space-y-2">
            {revenue.map((r: { name: string; amount: number }, i: number) => (
              <div key={i} className="flex justify-between text-sm">
                <span className="text-white/60">{r.name}</span>
                <span className="text-white font-mono">{fmt(r.amount)}</span>
              </div>
            ))}
            {revenue.length === 0 && <p className="text-white/30 text-sm">No revenue</p>}
          </div>
        </GlassCard>
        <GlassCard>
          <h4 className="text-sm font-semibold text-red-400 mb-3">Expenses</h4>
          <div className="space-y-2">
            {expenses.map((e: { name: string; amount: number }, i: number) => (
              <div key={i} className="flex justify-between text-sm">
                <span className="text-white/60">{e.name}</span>
                <span className="text-white font-mono">{fmt(e.amount)}</span>
              </div>
            ))}
            {expenses.length === 0 && <p className="text-white/30 text-sm">No expenses</p>}
          </div>
        </GlassCard>
      </div>
    </div>
  )
}

function JournalEntries() {
  const { data, isLoading } = useQuery({
    queryKey: ['journal-entries'],
    queryFn: () => accountingApi.getEntries({ limit: 50 }).then(r => r.data),
  })

  if (isLoading) return <div className="flex items-center justify-center h-48"><div className="w-8 h-8 border-2 border-indigo-500 border-t-transparent rounded-full animate-spin" /></div>

  const entries: { id: string; date: string; description: string; entry_type: string; is_void: boolean; lines: { account_name: string; debit: number; credit: number }[] }[] = data?.entries ?? []

  return (
    <GlassCard>
      <h3 className="text-base font-semibold text-white mb-4">Journal Entries</h3>
      <div className="space-y-3">
        {entries.map(e => (
          <div key={e.id} className={`rounded-xl border p-3 ${e.is_void ? 'opacity-50 border-white/5 bg-white/3' : 'border-white/10 bg-white/5'}`}>
            <div className="flex items-start justify-between mb-2">
              <div>
                <p className="text-sm font-medium text-white">{e.description}</p>
                <p className="text-xs text-white/40 mt-0.5">{new Date(e.date).toLocaleDateString()} · {e.entry_type}</p>
              </div>
              {e.is_void && <span className="text-xs px-2 py-0.5 rounded-full bg-red-500/15 border border-red-500/30 text-red-400">Voided</span>}
            </div>
            <div className="grid grid-cols-3 gap-1 text-xs text-white/40 mb-1 px-1">
              <span>Account</span><span className="text-right">Debit</span><span className="text-right">Credit</span>
            </div>
            {e.lines?.map((l, i) => (
              <div key={i} className="grid grid-cols-3 gap-1 text-xs px-1">
                <span className="text-white/60 truncate">{l.account_name}</span>
                <span className="text-right font-mono text-emerald-400">{l.debit ? fmt(l.debit) : ''}</span>
                <span className="text-right font-mono text-red-400">{l.credit ? fmt(l.credit) : ''}</span>
              </div>
            ))}
          </div>
        ))}
        {entries.length === 0 && <div className="text-center py-8 text-white/30 text-sm">No journal entries</div>}
      </div>
    </GlassCard>
  )
}

export default function AccountingPage() {
  const [tab, setTab] = useState<Tab>('Income Statement')

  const tabIcons: Record<Tab, React.ReactNode> = {
    'Trial Balance':     <ScaleIcon className="w-4 h-4" />,
    'Income Statement':  <ArrowTrendingUpIcon className="w-4 h-4" />,
    'Balance Sheet':     <BanknotesIcon className="w-4 h-4" />,
    'Journal Entries':   <BookOpenIcon className="w-4 h-4" />,
  }

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-xl font-bold text-white">Accounting</h2>
        <p className="text-white/40 text-sm mt-0.5">Double-entry ledger & financial reports</p>
      </div>

      {/* Tab bar */}
      <div className="flex gap-2 flex-wrap">
        {TABS.map(t => (
          <GlassButton
            key={t}
            variant={tab === t ? 'primary' : 'ghost'}
            icon={tabIcons[t]}
            onClick={() => setTab(t)}
          >
            {t}
          </GlassButton>
        ))}
      </div>

      {tab === 'Trial Balance'    && <TrialBalance />}
      {tab === 'Income Statement' && <IncomeStatement />}
      {tab === 'Balance Sheet'    && <BalanceSheet />}
      {tab === 'Journal Entries'  && <JournalEntries />}
    </div>
  )
}

function BalanceSheet() {
  const { data, isLoading } = useQuery({
    queryKey: ['balance-sheet'],
    queryFn: () => accountingApi.getBalanceSheet({ as_of: new Date().toISOString().split('T')[0] }).then(r => r.data),
  })

  if (isLoading) return <div className="flex items-center justify-center h-48"><div className="w-8 h-8 border-2 border-indigo-500 border-t-transparent rounded-full animate-spin" /></div>

  return (
    <div className="grid md:grid-cols-2 gap-4">
      <GlassCard>
        <h4 className="text-sm font-semibold text-indigo-400 mb-3">Assets</h4>
        <div className="space-y-2">
          {(data?.assets ?? []).map((a: { name: string; balance: number }, i: number) => (
            <div key={i} className="flex justify-between text-sm">
              <span className="text-white/60">{a.name}</span>
              <span className="text-white font-mono">{fmt(a.balance)}</span>
            </div>
          ))}
          <div className="border-t border-white/10 pt-2 flex justify-between text-sm font-semibold">
            <span className="text-white">Total Assets</span>
            <span className="text-white font-mono">{fmt(data?.total_assets ?? 0)}</span>
          </div>
        </div>
      </GlassCard>
      <div className="space-y-4">
        <GlassCard>
          <h4 className="text-sm font-semibold text-red-400 mb-3">Liabilities</h4>
          <div className="space-y-2">
            {(data?.liabilities ?? []).map((l: { name: string; balance: number }, i: number) => (
              <div key={i} className="flex justify-between text-sm">
                <span className="text-white/60">{l.name}</span>
                <span className="text-white font-mono">{fmt(l.balance)}</span>
              </div>
            ))}
            <div className="border-t border-white/10 pt-2 flex justify-between text-sm font-semibold">
              <span className="text-white">Total Liabilities</span>
              <span className="text-white font-mono">{fmt(data?.total_liabilities ?? 0)}</span>
            </div>
          </div>
        </GlassCard>
        <GlassCard>
          <h4 className="text-sm font-semibold text-purple-400 mb-3">Equity</h4>
          <div className="border-t border-white/10 pt-2 flex justify-between text-sm font-semibold">
            <span className="text-white">Total Equity</span>
            <span className="text-white font-mono">{fmt(data?.total_equity ?? 0)}</span>
          </div>
        </GlassCard>
      </div>
    </div>
  )
}
