import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { motion } from 'framer-motion'
import {
  UserGroupIcon, PlusIcon, MagnifyingGlassIcon,
  EnvelopeIcon, PhoneIcon, BuildingOfficeIcon,
} from '@heroicons/react/24/outline'
import { GlassCard } from '../../components/ui/GlassCard'
import { GlassButton } from '../../components/ui/GlassButton'
import { GlassBadge, type BadgeStatus } from '../../components/ui/GlassBadge'
import { ownersApi } from '../../services/api'

interface Owner {
  id: string
  first_name: string
  last_name: string
  email: string
  phone?: string
  property_count?: number
  status?: string
}

function OwnerModal({ onClose, onSave }: { onClose: () => void; onSave: (data: object) => void }) {
  const [form, setForm] = useState({ first_name: '', last_name: '', email: '', phone: '', notes: '' })
  const set = (k: string) => (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) =>
    setForm(f => ({ ...f, [k]: e.target.value }))

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4">
      <motion.div initial={{ opacity: 0, scale: 0.95 }} animate={{ opacity: 1, scale: 1 }} className="w-full max-w-md">
        <GlassCard>
          <h3 className="text-lg font-semibold text-white mb-5">Add Owner</h3>
          <div className="space-y-3">
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="text-xs text-white/50 mb-1 block">First Name</label>
                <input value={form.first_name} onChange={set('first_name')} className="w-full bg-white/8 border border-white/15 rounded-xl px-3 py-2 text-sm text-white focus:outline-none focus:border-indigo-500/60" />
              </div>
              <div>
                <label className="text-xs text-white/50 mb-1 block">Last Name</label>
                <input value={form.last_name} onChange={set('last_name')} className="w-full bg-white/8 border border-white/15 rounded-xl px-3 py-2 text-sm text-white focus:outline-none focus:border-indigo-500/60" />
              </div>
            </div>
            <div>
              <label className="text-xs text-white/50 mb-1 block">Email</label>
              <input type="email" value={form.email} onChange={set('email')} className="w-full bg-white/8 border border-white/15 rounded-xl px-3 py-2 text-sm text-white focus:outline-none focus:border-indigo-500/60" />
            </div>
            <div>
              <label className="text-xs text-white/50 mb-1 block">Phone</label>
              <input value={form.phone} onChange={set('phone')} className="w-full bg-white/8 border border-white/15 rounded-xl px-3 py-2 text-sm text-white focus:outline-none focus:border-indigo-500/60" />
            </div>
            <div>
              <label className="text-xs text-white/50 mb-1 block">Notes</label>
              <textarea value={form.notes} onChange={set('notes')} rows={2} className="w-full bg-white/8 border border-white/15 rounded-xl px-3 py-2 text-sm text-white focus:outline-none focus:border-indigo-500/60 resize-none" />
            </div>
          </div>
          <div className="flex gap-3 mt-5">
            <GlassButton className="flex-1" onClick={onClose}>Cancel</GlassButton>
            <GlassButton variant="primary" className="flex-1" onClick={() => onSave(form)}>Add Owner</GlassButton>
          </div>
        </GlassCard>
      </motion.div>
    </div>
  )
}

export default function OwnersPage() {
  const [search, setSearch] = useState('')
  const [showModal, setShowModal] = useState(false)
  const qc = useQueryClient()

  const { data, isLoading } = useQuery({
    queryKey: ['owners', search],
    queryFn: () => ownersApi.list({ search: search || undefined, limit: 50 }).then(r => r.data),
  })

  const createMutation = useMutation({
    mutationFn: (d: object) => ownersApi.create(d),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['owners'] }); setShowModal(false) },
  })

  return (
    <div className="space-y-6">
      {showModal && (
        <OwnerModal
          onClose={() => setShowModal(false)}
          onSave={(d) => createMutation.mutate(d)}
        />
      )}

      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-bold text-white">Owners</h2>
          <p className="text-white/40 text-sm mt-0.5">{data?.total ?? 0} registered</p>
        </div>
        <GlassButton variant="primary" icon={<PlusIcon className="w-4 h-4" />} onClick={() => setShowModal(true)}>
          Add Owner
        </GlassButton>
      </div>

      {/* Search */}
      <GlassCard className="flex gap-3">
        <div className="relative flex-1">
          <MagnifyingGlassIcon className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-white/40" />
          <input
            value={search}
            onChange={e => setSearch(e.target.value)}
            placeholder="Search owners by name or email…"
            className="w-full bg-white/8 border border-white/15 rounded-xl pl-9 pr-4 py-2 text-sm text-white placeholder-white/30 focus:outline-none focus:border-indigo-500/60"
          />
        </div>
      </GlassCard>

      {/* Owner list */}
      {isLoading ? (
        <div className="flex items-center justify-center h-48">
          <div className="w-8 h-8 border-2 border-indigo-500 border-t-transparent rounded-full animate-spin" />
        </div>
      ) : (
        <div className="grid sm:grid-cols-2 xl:grid-cols-3 gap-4">
          {(data?.owners ?? []).map((owner: Owner, i: number) => (
            <motion.div key={owner.id} initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.04 }}>
              <GlassCard hover>
                <div className="flex items-start justify-between mb-3">
                  <div className="w-10 h-10 rounded-full bg-gradient-to-br from-indigo-500 to-purple-600 flex items-center justify-center text-white font-semibold text-sm">
                    {owner.first_name?.[0]}{owner.last_name?.[0]}
                  </div>
                  <GlassBadge status={(owner.status ?? 'active') as BadgeStatus} />
                </div>
                <h3 className="font-semibold text-white">{owner.first_name} {owner.last_name}</h3>
                <div className="mt-2 space-y-1">
                  <div className="flex items-center gap-2 text-sm text-white/50">
                    <EnvelopeIcon className="w-3.5 h-3.5 shrink-0" />
                    <span className="truncate">{owner.email}</span>
                  </div>
                  {owner.phone && (
                    <div className="flex items-center gap-2 text-sm text-white/50">
                      <PhoneIcon className="w-3.5 h-3.5 shrink-0" />
                      <span>{owner.phone}</span>
                    </div>
                  )}
                  <div className="flex items-center gap-2 text-sm text-white/50">
                    <BuildingOfficeIcon className="w-3.5 h-3.5 shrink-0" />
                    <span>{owner.property_count ?? 0} properties</span>
                  </div>
                </div>
              </GlassCard>
            </motion.div>
          ))}
        </div>
      )}

      {!isLoading && (data?.total === 0 || !data) && (
        <div className="text-center py-16 text-white/30">
          <UserGroupIcon className="w-12 h-12 mx-auto mb-3 opacity-30" />
          <p>No owners found</p>
        </div>
      )}
    </div>
  )
}
