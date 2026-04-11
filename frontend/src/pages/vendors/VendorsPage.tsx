import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { motion } from 'framer-motion'
import {
  WrenchScrewdriverIcon, PlusIcon, MagnifyingGlassIcon,
  StarIcon, PhoneIcon, EnvelopeIcon,
} from '@heroicons/react/24/outline'
import { GlassCard } from '../../components/ui/GlassCard'
import { GlassButton } from '../../components/ui/GlassButton'
import { GlassBadge, type BadgeStatus } from '../../components/ui/GlassBadge'
import { vendorsApi } from '../../services/api'

interface Vendor {
  id: string
  name: string
  contact_name?: string
  email?: string
  phone?: string
  trade_specialties?: string[]
  rating?: number
  status?: string
  license_number?: string
  insurance_verified?: boolean
}

const TRADES = ['plumbing', 'electrical', 'hvac', 'roofing', 'landscaping', 'general', 'painting', 'carpentry']

function VendorModal({ onClose, onSave }: { onClose: () => void; onSave: (d: object) => void }) {
  const [form, setForm] = useState({
    name: '', contact_name: '', email: '', phone: '', license_number: '', trade_specialties: [] as string[],
  })
  const set = (k: string) => (e: React.ChangeEvent<HTMLInputElement>) => setForm(f => ({ ...f, [k]: e.target.value }))
  const toggleTrade = (t: string) =>
    setForm(f => ({ ...f, trade_specialties: f.trade_specialties.includes(t) ? f.trade_specialties.filter(x => x !== t) : [...f.trade_specialties, t] }))

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4">
      <motion.div initial={{ opacity: 0, scale: 0.95 }} animate={{ opacity: 1, scale: 1 }} className="w-full max-w-md">
        <GlassCard>
          <h3 className="text-lg font-semibold text-white mb-5">Add Vendor</h3>
          <div className="space-y-3">
            <div>
              <label className="text-xs text-white/50 mb-1 block">Company Name *</label>
              <input value={form.name} onChange={set('name')} className="w-full bg-white/8 border border-white/15 rounded-xl px-3 py-2 text-sm text-white focus:outline-none focus:border-indigo-500/60" />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="text-xs text-white/50 mb-1 block">Contact Name</label>
                <input value={form.contact_name} onChange={set('contact_name')} className="w-full bg-white/8 border border-white/15 rounded-xl px-3 py-2 text-sm text-white focus:outline-none focus:border-indigo-500/60" />
              </div>
              <div>
                <label className="text-xs text-white/50 mb-1 block">Phone</label>
                <input value={form.phone} onChange={set('phone')} className="w-full bg-white/8 border border-white/15 rounded-xl px-3 py-2 text-sm text-white focus:outline-none focus:border-indigo-500/60" />
              </div>
            </div>
            <div>
              <label className="text-xs text-white/50 mb-1 block">Email</label>
              <input type="email" value={form.email} onChange={set('email')} className="w-full bg-white/8 border border-white/15 rounded-xl px-3 py-2 text-sm text-white focus:outline-none focus:border-indigo-500/60" />
            </div>
            <div>
              <label className="text-xs text-white/50 mb-1 block">License #</label>
              <input value={form.license_number} onChange={set('license_number')} className="w-full bg-white/8 border border-white/15 rounded-xl px-3 py-2 text-sm text-white focus:outline-none focus:border-indigo-500/60" />
            </div>
            <div>
              <label className="text-xs text-white/50 mb-2 block">Trade Specialties</label>
              <div className="flex flex-wrap gap-2">
                {TRADES.map(t => (
                  <button
                    key={t}
                    onClick={() => toggleTrade(t)}
                    className={`px-3 py-1 rounded-full text-xs font-medium border transition-colors ${
                      form.trade_specialties.includes(t)
                        ? 'bg-indigo-500/30 border-indigo-500/60 text-indigo-300'
                        : 'bg-white/5 border-white/15 text-white/50 hover:border-white/30'
                    }`}
                  >
                    {t}
                  </button>
                ))}
              </div>
            </div>
          </div>
          <div className="flex gap-3 mt-5">
            <GlassButton className="flex-1" onClick={onClose}>Cancel</GlassButton>
            <GlassButton variant="primary" className="flex-1" onClick={() => onSave(form)}>Add Vendor</GlassButton>
          </div>
        </GlassCard>
      </motion.div>
    </div>
  )
}

export default function VendorsPage() {
  const [search, setSearch] = useState('')
  const [tradeFilter, setTradeFilter] = useState('')
  const [showModal, setShowModal] = useState(false)
  const qc = useQueryClient()

  const { data, isLoading } = useQuery({
    queryKey: ['vendors', search, tradeFilter],
    queryFn: () => vendorsApi.list({ search: search || undefined, trade: tradeFilter || undefined, limit: 50 }).then(r => r.data),
  })

  const createMutation = useMutation({
    mutationFn: (d: object) => vendorsApi.create(d),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['vendors'] }); setShowModal(false) },
  })

  return (
    <div className="space-y-6">
      {showModal && <VendorModal onClose={() => setShowModal(false)} onSave={d => createMutation.mutate(d)} />}

      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-bold text-white">Vendors</h2>
          <p className="text-white/40 text-sm mt-0.5">{data?.total ?? 0} registered</p>
        </div>
        <GlassButton variant="primary" icon={<PlusIcon className="w-4 h-4" />} onClick={() => setShowModal(true)}>
          Add Vendor
        </GlassButton>
      </div>

      <GlassCard className="flex flex-wrap gap-3">
        <div className="relative flex-1 min-w-48">
          <MagnifyingGlassIcon className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-white/40" />
          <input
            value={search}
            onChange={e => setSearch(e.target.value)}
            placeholder="Search vendors…"
            className="w-full bg-white/8 border border-white/15 rounded-xl pl-9 pr-4 py-2 text-sm text-white placeholder-white/30 focus:outline-none focus:border-indigo-500/60"
          />
        </div>
        <select
          value={tradeFilter}
          onChange={e => setTradeFilter(e.target.value)}
          className="bg-white/8 border border-white/15 rounded-xl px-3 py-2 text-sm text-white focus:outline-none"
        >
          <option value="">All Trades</option>
          {TRADES.map(t => <option key={t} value={t} className="capitalize">{t}</option>)}
        </select>
      </GlassCard>

      {isLoading ? (
        <div className="flex items-center justify-center h-48">
          <div className="w-8 h-8 border-2 border-indigo-500 border-t-transparent rounded-full animate-spin" />
        </div>
      ) : (
        <div className="grid sm:grid-cols-2 xl:grid-cols-3 gap-4">
          {(data?.vendors ?? []).map((v: Vendor, i: number) => (
            <motion.div key={v.id} initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.04 }}>
              <GlassCard hover>
                <div className="flex items-start justify-between mb-3">
                  <div className="p-2.5 rounded-xl bg-amber-500/15 border border-amber-500/20">
                    <WrenchScrewdriverIcon className="w-5 h-5 text-amber-400" />
                  </div>
                  <div className="flex items-center gap-1.5">
                    {v.insurance_verified && (
                      <span className="text-xs px-2 py-0.5 rounded-full bg-emerald-500/15 border border-emerald-500/30 text-emerald-400">Insured</span>
                    )}
                    <GlassBadge status={(v.status ?? 'active') as BadgeStatus} />
                  </div>
                </div>
                <h3 className="font-semibold text-white">{v.name}</h3>
                {v.contact_name && <p className="text-white/40 text-xs mt-0.5">{v.contact_name}</p>}
                <div className="mt-2 space-y-1.5">
                  {v.email && (
                    <div className="flex items-center gap-2 text-sm text-white/50">
                      <EnvelopeIcon className="w-3.5 h-3.5 shrink-0" />
                      <span className="truncate">{v.email}</span>
                    </div>
                  )}
                  {v.phone && (
                    <div className="flex items-center gap-2 text-sm text-white/50">
                      <PhoneIcon className="w-3.5 h-3.5 shrink-0" />
                      <span>{v.phone}</span>
                    </div>
                  )}
                  {v.rating && (
                    <div className="flex items-center gap-1 text-sm text-amber-400">
                      <StarIcon className="w-3.5 h-3.5" />
                      <span>{v.rating.toFixed(1)}</span>
                    </div>
                  )}
                  {v.trade_specialties && v.trade_specialties.length > 0 && (
                    <div className="flex flex-wrap gap-1 mt-2">
                      {v.trade_specialties.slice(0, 3).map(t => (
                        <span key={t} className="text-xs px-2 py-0.5 rounded-full bg-white/8 border border-white/10 text-white/50 capitalize">{t}</span>
                      ))}
                    </div>
                  )}
                </div>
              </GlassCard>
            </motion.div>
          ))}
        </div>
      )}

      {!isLoading && (data?.total === 0 || !data) && (
        <div className="text-center py-16 text-white/30">
          <WrenchScrewdriverIcon className="w-12 h-12 mx-auto mb-3 opacity-30" />
          <p>No vendors found</p>
        </div>
      )}
    </div>
  )
}
