import { useState } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { ArrowLeftIcon } from '@heroicons/react/24/outline'
import { GlassCard } from '../../components/ui/GlassCard'
import { GlassButton } from '../../components/ui/GlassButton'
import { propertiesApi } from '../../services/api'

const inputClass =
  'w-full bg-white/8 border border-white/15 rounded-xl px-4 py-2 text-sm text-white placeholder-white/30 focus:outline-none focus:border-indigo-500/60'
const labelClass = 'block text-xs font-medium text-white/50 mb-1'

export default function AddPropertyPage() {
  const navigate = useNavigate()
  const qc = useQueryClient()
  const [error, setError] = useState('')

  const [form, setForm] = useState({
    name: '',
    property_type: 'single_family',
    status: 'active',
    street: '',
    unit: '',
    city: '',
    state: '',
    zip_code: '',
    country: 'US',
    year_built: '',
    square_feet: '',
    bedrooms: '',
    bathrooms: '',
    monthly_rent: '',
    notes: '',
  })

  const mutation = useMutation({
    mutationFn: (data: object) => propertiesApi.create(data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['properties'] })
      navigate('/properties')
    },
    onError: (err: any) => {
      setError(err?.response?.data?.detail ?? 'Failed to create property')
    },
  })

  function set(field: string, value: string) {
    setForm(f => ({ ...f, [field]: value }))
  }

  function handleInput(field: string) {
    return (e: React.FormEvent<HTMLInputElement | HTMLTextAreaElement>) => {
      const target = e.target as HTMLInputElement | HTMLTextAreaElement
      set(field, target.value)
    }
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError('')

    const payload: any = {
      name: form.name,
      property_type: form.property_type,
      status: form.status,
      address: {
        street: form.street,
        city: form.city,
        state: form.state,
        zip_code: form.zip_code,
        country: form.country,
        ...(form.unit ? { unit: form.unit } : {}),
      },
      ...(form.year_built   ? { year_built:   parseInt(form.year_built)     } : {}),
      ...(form.square_feet  ? { square_feet:  parseFloat(form.square_feet)  } : {}),
      ...(form.bedrooms     ? { bedrooms:     parseInt(form.bedrooms)       } : {}),
      ...(form.bathrooms    ? { bathrooms:    parseFloat(form.bathrooms)    } : {}),
      ...(form.monthly_rent ? { monthly_rent: parseFloat(form.monthly_rent) } : {}),
      ...(form.notes        ? { notes: form.notes }                          : {}),
    }

    mutation.mutate(payload)
  }

  return (
    <div className="max-w-2xl mx-auto space-y-6">
      <div className="flex items-center gap-3">
        <Link to="/properties">
          <button className="p-2 rounded-xl bg-white/8 border border-white/15 text-white/60 hover:text-white transition-colors">
            <ArrowLeftIcon className="w-4 h-4" />
          </button>
        </Link>
        <div>
          <h2 className="text-xl font-bold text-white">Add Property</h2>
          <p className="text-white/40 text-sm mt-0.5">Fill in the details below</p>
        </div>
      </div>

      <form onSubmit={handleSubmit} className="space-y-4">
        {/* Basic info */}
        <GlassCard className="space-y-4">
          <h3 className="text-sm font-semibold text-white/70">Basic Information</h3>
          <div>
            <label className={labelClass}>Property Name *</label>
            <input autoFocus required type="text" name="property_name" inputMode="text" className={inputClass} placeholder="e.g. Oak Street Duplex"
              value={form.name} onChange={e => set('name', e.target.value)} onInput={handleInput('name')} />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className={labelClass}>Property Type *</label>
              <select required className={inputClass} value={form.property_type}
                onChange={e => set('property_type', e.target.value)}>
                <option value="single_family">Single Family</option>
                <option value="multi_family">Multi-Family</option>
                <option value="commercial">Commercial</option>
                <option value="condo">Condo</option>
                <option value="townhouse">Townhouse</option>
                <option value="land">Land</option>
              </select>
            </div>
            <div>
              <label className={labelClass}>Status</label>
              <select className={inputClass} value={form.status}
                onChange={e => set('status', e.target.value)}>
                <option value="active">Active</option>
                <option value="vacant">Vacant</option>
                <option value="listed">Listed</option>
                <option value="under_maintenance">Under Maintenance</option>
                <option value="inactive">Inactive</option>
              </select>
            </div>
          </div>
        </GlassCard>

        {/* Address */}
        <GlassCard className="space-y-4">
          <h3 className="text-sm font-semibold text-white/70">Address</h3>
          <div className="grid grid-cols-3 gap-3">
            <div className="col-span-2">
              <label className={labelClass}>Street *</label>
              <input required className={inputClass} placeholder="123 Main St"
                value={form.street} onChange={e => set('street', e.target.value)} />
            </div>
            <div>
              <label className={labelClass}>Unit / Apt</label>
              <input className={inputClass} placeholder="Unit 2B"
                value={form.unit} onChange={e => set('unit', e.target.value)} />
            </div>
          </div>
          <div className="grid grid-cols-3 gap-3">
            <div>
              <label className={labelClass}>City *</label>
              <input required className={inputClass} placeholder="Chicago"
                value={form.city} onChange={e => set('city', e.target.value)} />
            </div>
            <div>
              <label className={labelClass}>State *</label>
              <input required className={inputClass} placeholder="IL" maxLength={2}
                value={form.state} onChange={e => set('state', e.target.value.toUpperCase())} />
            </div>
            <div>
              <label className={labelClass}>ZIP *</label>
              <input required className={inputClass} placeholder="60601"
                value={form.zip_code} onChange={e => set('zip_code', e.target.value)} />
            </div>
          </div>
        </GlassCard>

        {/* Details */}
        <GlassCard className="space-y-4">
          <h3 className="text-sm font-semibold text-white/70">Property Details</h3>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className={labelClass}>Bedrooms</label>
              <input type="number" min="0" className={inputClass} placeholder="3"
                value={form.bedrooms} onChange={e => set('bedrooms', e.target.value)} />
            </div>
            <div>
              <label className={labelClass}>Bathrooms</label>
              <input type="number" min="0" step="0.5" className={inputClass} placeholder="2"
                value={form.bathrooms} onChange={e => set('bathrooms', e.target.value)} />
            </div>
            <div>
              <label className={labelClass}>Square Feet</label>
              <input type="number" min="0" className={inputClass} placeholder="1400"
                value={form.square_feet} onChange={e => set('square_feet', e.target.value)} />
            </div>
            <div>
              <label className={labelClass}>Year Built</label>
              <input type="number" min="1800" max={new Date().getFullYear()} className={inputClass} placeholder="1995"
                value={form.year_built} onChange={e => set('year_built', e.target.value)} />
            </div>
          </div>
          <div>
            <label className={labelClass}>Monthly Rent ($)</label>
            <input type="number" min="0" step="0.01" className={inputClass} placeholder="2500"
              value={form.monthly_rent} onChange={e => set('monthly_rent', e.target.value)} />
          </div>
          <div>
            <label className={labelClass}>Notes</label>
            <textarea rows={3} className={inputClass} placeholder="Any additional notes…"
              value={form.notes} onChange={e => set('notes', e.target.value)} />
          </div>
        </GlassCard>

        {error && (
          <p className="text-red-400 text-sm text-center">{error}</p>
        )}

        <div className="flex gap-3 justify-end">
          <Link to="/properties">
            <GlassButton type="button" variant="secondary">Cancel</GlassButton>
          </Link>
          <GlassButton type="submit" variant="primary" disabled={mutation.isPending}>
            {mutation.isPending ? 'Saving…' : 'Add Property'}
          </GlassButton>
        </div>
      </form>
    </div>
  )
}
