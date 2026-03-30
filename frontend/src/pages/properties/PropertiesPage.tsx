import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { motion } from 'framer-motion'
import { PlusIcon, MagnifyingGlassIcon, BuildingOfficeIcon } from '@heroicons/react/24/outline'
import { GlassCard } from '../../components/ui/GlassCard'
import { GlassButton } from '../../components/ui/GlassButton'
import { GlassBadge } from '../../components/ui/GlassBadge'
import { propertiesApi } from '../../services/api'

export default function PropertiesPage() {
  const [search, setSearch] = useState('')
  const [typeFilter, setTypeFilter] = useState('')

  const { data, isLoading } = useQuery({
    queryKey: ['properties', search, typeFilter],
    queryFn: () => propertiesApi.list({ search: search || undefined, property_type: typeFilter || undefined, limit: 50 }).then(r => r.data),
  })

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-bold text-white">Properties</h2>
          <p className="text-white/40 text-sm mt-0.5">{data?.total ?? 0} total</p>
        </div>
        <Link to="/properties/new">
          <GlassButton variant="primary" icon={<PlusIcon className="w-4 h-4" />}>Add Property</GlassButton>
        </Link>
      </div>

      {/* Filters */}
      <GlassCard className="flex flex-wrap gap-3">
        <div className="relative flex-1 min-w-48">
          <MagnifyingGlassIcon className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-white/40" />
          <input
            value={search}
            onChange={e => setSearch(e.target.value)}
            placeholder="Search properties…"
            className="w-full bg-white/8 border border-white/15 rounded-xl pl-9 pr-4 py-2 text-sm text-white placeholder-white/30 focus:outline-none focus:border-indigo-500/60"
          />
        </div>
        <select
          value={typeFilter}
          onChange={e => setTypeFilter(e.target.value)}
          className="bg-white/8 border border-white/15 rounded-xl px-3 py-2 text-sm text-white focus:outline-none"
        >
          <option value="">All Types</option>
          <option value="single_family">Single Family</option>
          <option value="multi_family">Multi-Family</option>
          <option value="commercial">Commercial</option>
          <option value="condo">Condo</option>
        </select>
      </GlassCard>

      {/* Grid */}
      {isLoading ? (
        <div className="flex items-center justify-center h-48">
          <div className="w-8 h-8 border-2 border-indigo-500 border-t-transparent rounded-full animate-spin" />
        </div>
      ) : (
        <div className="grid sm:grid-cols-2 xl:grid-cols-3 gap-4">
          {(data?.properties ?? []).map((p: any, i: number) => (
            <motion.div key={p.id} initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.04 }}>
              <Link to={`/properties/${p.id}`}>
                <GlassCard hover className="h-full">
                  <div className="flex items-start justify-between mb-3">
                    <div className="p-2.5 rounded-xl bg-indigo-500/15 border border-indigo-500/20">
                      <BuildingOfficeIcon className="w-5 h-5 text-indigo-400" />
                    </div>
                    <GlassBadge status={p.status} />
                  </div>
                  <h3 className="font-semibold text-white text-base mb-1">{p.name}</h3>
                  <p className="text-white/40 text-sm mb-3">
                    {p.address?.street}, {p.address?.city}, {p.address?.state}
                  </p>
                  <div className="flex items-center justify-between text-sm">
                    <span className="text-white/40 capitalize">{p.property_type?.replace('_', ' ')}</span>
                    {p.monthly_rent && (
                      <span className="text-emerald-400 font-semibold">${p.monthly_rent.toLocaleString()}/mo</span>
                    )}
                  </div>
                </GlassCard>
              </Link>
            </motion.div>
          ))}
        </div>
      )}

      {data?.total === 0 && !isLoading && (
        <div className="text-center py-16 text-white/30">
          <BuildingOfficeIcon className="w-12 h-12 mx-auto mb-3 opacity-30" />
          <p>No properties found</p>
        </div>
      )}
    </div>
  )
}
