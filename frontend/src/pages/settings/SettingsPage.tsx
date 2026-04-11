import { useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import {
  UserCircleIcon, BellIcon, ShieldCheckIcon, CogIcon,
  CheckIcon, KeyIcon,
} from '@heroicons/react/24/outline'
import { GlassCard } from '../../components/ui/GlassCard'
import { GlassButton } from '../../components/ui/GlassButton'
import { useAuthStore } from '../../store/authStore'
import { api } from '../../services/api'

const TABS = ['Profile', 'Notifications', 'Security', 'System'] as const
type Tab = (typeof TABS)[number]

const tabIcons: Record<Tab, React.ReactNode> = {
  Profile: <UserCircleIcon className="w-4 h-4" />,
  Notifications: <BellIcon className="w-4 h-4" />,
  Security: <ShieldCheckIcon className="w-4 h-4" />,
  System: <CogIcon className="w-4 h-4" />,
}

function ProfileTab() {
  const { user, setUser } = useAuthStore()
  const [form, setForm] = useState({
    first_name: user?.first_name ?? '',
    last_name: user?.last_name ?? '',
    email: user?.email ?? '',
    phone: (user as any)?.phone ?? '',
  })
  const [saved, setSaved] = useState(false)

  const set = (k: string) => (e: React.ChangeEvent<HTMLInputElement>) => setForm(f => ({ ...f, [k]: e.target.value }))

  const mutation = useMutation({
    mutationFn: () => api.put('/auth/me', form).then(r => r.data),
    onSuccess: (data) => { setUser(data); setSaved(true); setTimeout(() => setSaved(false), 2000) },
  })

  return (
    <GlassCard className="max-w-lg">
      <h3 className="text-base font-semibold text-white mb-5">Profile</h3>
      <div className="flex items-center gap-4 mb-6">
        <div className="w-16 h-16 rounded-full bg-gradient-to-br from-indigo-500 to-purple-600 flex items-center justify-center text-white text-xl font-bold">
          {user?.first_name?.[0]}{user?.last_name?.[0]}
        </div>
        <div>
          <p className="text-white font-medium">{user?.first_name} {user?.last_name}</p>
          <p className="text-white/40 text-sm capitalize">{user?.role}</p>
          {user?.is_google_auth && (
            <span className="text-xs px-2 py-0.5 mt-1 inline-block rounded-full bg-blue-500/15 border border-blue-500/30 text-blue-400">Google Account</span>
          )}
        </div>
      </div>
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
          <input type="email" value={form.email} onChange={set('email')} disabled={!!user?.is_google_auth} className="w-full bg-white/8 border border-white/15 rounded-xl px-3 py-2 text-sm text-white focus:outline-none focus:border-indigo-500/60 disabled:opacity-40 disabled:cursor-not-allowed" />
        </div>
        <div>
          <label className="text-xs text-white/50 mb-1 block">Phone</label>
          <input value={form.phone} onChange={set('phone')} className="w-full bg-white/8 border border-white/15 rounded-xl px-3 py-2 text-sm text-white focus:outline-none focus:border-indigo-500/60" />
        </div>
      </div>
      <div className="mt-5">
        <GlassButton
          variant="primary"
          icon={saved ? <CheckIcon className="w-4 h-4" /> : undefined}
          onClick={() => mutation.mutate()}
          disabled={mutation.isPending}
        >
          {saved ? 'Saved!' : mutation.isPending ? 'Saving…' : 'Save Changes'}
        </GlassButton>
      </div>
    </GlassCard>
  )
}

function NotificationsTab() {
  const [prefs, setPrefs] = useState({
    email_maintenance: true,
    email_invoices: true,
    email_lease_expiry: true,
    push_maintenance: false,
    push_invoices: false,
  })

  const toggle = (k: keyof typeof prefs) => setPrefs(p => ({ ...p, [k]: !p[k] }))

  const items = [
    { key: 'email_maintenance', label: 'Maintenance updates', desc: 'Work order status changes', channel: 'Email' },
    { key: 'email_invoices', label: 'Invoice activity', desc: 'New invoices and payment confirmations', channel: 'Email' },
    { key: 'email_lease_expiry', label: 'Lease expiry alerts', desc: '60/30/7 day warnings', channel: 'Email' },
    { key: 'push_maintenance', label: 'Maintenance push', desc: 'Urgent work order alerts', channel: 'Push' },
    { key: 'push_invoices', label: 'Invoice push', desc: 'Overdue invoice alerts', channel: 'Push' },
  ] as const

  return (
    <GlassCard className="max-w-lg">
      <h3 className="text-base font-semibold text-white mb-5">Notification Preferences</h3>
      <div className="space-y-3">
        {items.map(item => (
          <div key={item.key} className="flex items-center justify-between py-2 border-b border-white/5 last:border-0">
            <div>
              <p className="text-sm text-white">{item.label}</p>
              <p className="text-xs text-white/40">{item.desc} · {item.channel}</p>
            </div>
            <button
              onClick={() => toggle(item.key as keyof typeof prefs)}
              className={`relative w-10 h-6 rounded-full transition-colors ${prefs[item.key] ? 'bg-indigo-500' : 'bg-white/15'}`}
            >
              <div className={`absolute top-1 w-4 h-4 bg-white rounded-full shadow transition-transform ${prefs[item.key] ? 'left-5' : 'left-1'}`} />
            </button>
          </div>
        ))}
      </div>
      <div className="mt-5">
        <GlassButton variant="primary">Save Preferences</GlassButton>
      </div>
    </GlassCard>
  )
}

function SecurityTab() {
  const { user } = useAuthStore()
  const [form, setForm] = useState({ current_password: '', new_password: '', confirm_password: '' })
  const set = (k: string) => (e: React.ChangeEvent<HTMLInputElement>) => setForm(f => ({ ...f, [k]: e.target.value }))

  const mutation = useMutation({
    mutationFn: () => api.post('/auth/change-password', { current_password: form.current_password, new_password: form.new_password }),
    onSuccess: () => setForm({ current_password: '', new_password: '', confirm_password: '' }),
  })

  return (
    <div className="space-y-4 max-w-lg">
      {!user?.is_google_auth && (
        <GlassCard>
          <div className="flex items-center gap-2 mb-5">
            <KeyIcon className="w-4 h-4 text-white/60" />
            <h3 className="text-base font-semibold text-white">Change Password</h3>
          </div>
          <div className="space-y-3">
            <div>
              <label className="text-xs text-white/50 mb-1 block">Current Password</label>
              <input type="password" value={form.current_password} onChange={set('current_password')} className="w-full bg-white/8 border border-white/15 rounded-xl px-3 py-2 text-sm text-white focus:outline-none focus:border-indigo-500/60" />
            </div>
            <div>
              <label className="text-xs text-white/50 mb-1 block">New Password</label>
              <input type="password" value={form.new_password} onChange={set('new_password')} className="w-full bg-white/8 border border-white/15 rounded-xl px-3 py-2 text-sm text-white focus:outline-none focus:border-indigo-500/60" />
            </div>
            <div>
              <label className="text-xs text-white/50 mb-1 block">Confirm Password</label>
              <input type="password" value={form.confirm_password} onChange={set('confirm_password')} className="w-full bg-white/8 border border-white/15 rounded-xl px-3 py-2 text-sm text-white focus:outline-none focus:border-indigo-500/60" />
            </div>
          </div>
          {mutation.isError && <p className="text-red-400 text-sm mt-2">Failed to change password. Check your current password.</p>}
          {mutation.isSuccess && <p className="text-emerald-400 text-sm mt-2">Password changed successfully.</p>}
          <div className="mt-5">
            <GlassButton
              variant="primary"
              onClick={() => mutation.mutate()}
              disabled={mutation.isPending || form.new_password !== form.confirm_password || !form.current_password}
            >
              {mutation.isPending ? 'Updating…' : 'Update Password'}
            </GlassButton>
          </div>
        </GlassCard>
      )}

      <GlassCard>
        <h3 className="text-base font-semibold text-white mb-4">Sessions</h3>
        <div className="flex items-center justify-between py-2">
          <div>
            <p className="text-sm text-white">Current session</p>
            <p className="text-xs text-white/40">This browser · Active now</p>
          </div>
          <span className="text-xs px-2 py-1 rounded-full bg-emerald-500/15 border border-emerald-500/30 text-emerald-400">Active</span>
        </div>
      </GlassCard>
    </div>
  )
}

function SystemTab() {
  const items = [
    { label: 'API Version', value: 'v1.0.0' },
    { label: 'Environment', value: import.meta.env.MODE },
    { label: 'API URL', value: import.meta.env.VITE_API_URL ?? 'same-origin' },
  ]

  return (
    <GlassCard className="max-w-lg">
      <h3 className="text-base font-semibold text-white mb-5">System Information</h3>
      <div className="space-y-3">
        {items.map(item => (
          <div key={item.label} className="flex justify-between py-2 border-b border-white/5 last:border-0 text-sm">
            <span className="text-white/50">{item.label}</span>
            <span className="text-white font-mono">{item.value}</span>
          </div>
        ))}
      </div>
    </GlassCard>
  )
}

export default function SettingsPage() {
  const [tab, setTab] = useState<Tab>('Profile')

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-xl font-bold text-white">Settings</h2>
        <p className="text-white/40 text-sm mt-0.5">Manage your account and preferences</p>
      </div>

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

      {tab === 'Profile'       && <ProfileTab />}
      {tab === 'Notifications' && <NotificationsTab />}
      {tab === 'Security'      && <SecurityTab />}
      {tab === 'System'        && <SystemTab />}
    </div>
  )
}
