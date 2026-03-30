import { useState } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { clsx } from 'clsx'
import { motion, AnimatePresence } from 'framer-motion'
import {
  HomeIcon, BuildingOfficeIcon, UsersIcon, CalculatorIcon,
  WrenchScrewdriverIcon, TruckIcon, DocumentTextIcon,
  BellIcon, SparklesIcon, Cog6ToothIcon, ChevronLeftIcon,
  ArrowRightOnRectangleIcon, ChevronRightIcon,
} from '@heroicons/react/24/outline'
import { useAuthStore } from '../../store/authStore'

const navGroups = [
  {
    label: 'Overview',
    items: [
      { to: '/dashboard', icon: HomeIcon, label: 'Dashboard' },
      { to: '/notifications', icon: BellIcon, label: 'Notifications' },
    ],
  },
  {
    label: 'Management',
    items: [
      { to: '/properties', icon: BuildingOfficeIcon, label: 'Properties' },
      { to: '/owners', icon: UsersIcon, label: 'Owners' },
      { to: '/tenants', icon: UsersIcon, label: 'Tenants' },
    ],
  },
  {
    label: 'Finance',
    items: [
      { to: '/accounting', icon: CalculatorIcon, label: 'Accounting' },
      { to: '/invoices', icon: DocumentTextIcon, label: 'Invoices' },
    ],
  },
  {
    label: 'Operations',
    items: [
      { to: '/maintenance', icon: WrenchScrewdriverIcon, label: 'Maintenance' },
      { to: '/vendors', icon: TruckIcon, label: 'Vendors' },
      { to: '/documents', icon: DocumentTextIcon, label: 'Documents' },
    ],
  },
  {
    label: 'AI',
    items: [
      { to: '/ai-search', icon: SparklesIcon, label: 'AI Search' },
    ],
  },
]

interface SidebarProps {
  mobileOpen: boolean
  onClose: () => void
}

export function Sidebar({ mobileOpen, onClose }: SidebarProps) {
  const [collapsed, setCollapsed] = useState(false)
  const location = useLocation()
  const { user, logout } = useAuthStore()

  const SidebarContent = () => (
    <div className="flex flex-col h-full">
      {/* Logo */}
      <div className="flex items-center justify-between p-4 border-b border-white/10">
        <AnimatePresence>
          {!collapsed && (
            <motion.div
              initial={{ opacity: 0, width: 0 }}
              animate={{ opacity: 1, width: 'auto' }}
              exit={{ opacity: 0, width: 0 }}
              className="flex items-center gap-2 overflow-hidden"
            >
              <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-indigo-500 to-purple-600 flex items-center justify-center text-white font-bold text-sm">
                E
              </div>
              <span className="font-bold text-white text-lg tracking-tight">Estatio</span>
            </motion.div>
          )}
        </AnimatePresence>
        {collapsed && (
          <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-indigo-500 to-purple-600 flex items-center justify-center text-white font-bold text-sm mx-auto">
            E
          </div>
        )}
        <button
          onClick={() => setCollapsed(!collapsed)}
          className="hidden lg:flex p-1.5 rounded-lg hover:bg-white/10 text-white/60 hover:text-white transition-colors"
        >
          {collapsed ? <ChevronRightIcon className="w-4 h-4" /> : <ChevronLeftIcon className="w-4 h-4" />}
        </button>
      </div>

      {/* Nav */}
      <nav className="flex-1 overflow-y-auto py-4 px-2 space-y-6">
        {navGroups.map((group) => (
          <div key={group.label}>
            {!collapsed && (
              <p className="px-3 mb-1 text-xs font-semibold text-white/30 uppercase tracking-widest">
                {group.label}
              </p>
            )}
            <ul className="space-y-0.5">
              {group.items.map((item) => {
                const active = location.pathname.startsWith(item.to)
                return (
                  <li key={item.to}>
                    <Link
                      to={item.to}
                      onClick={onClose}
                      title={collapsed ? item.label : undefined}
                      className={clsx(
                        'flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm font-medium transition-all duration-150',
                        active
                          ? 'bg-gradient-to-r from-indigo-500/30 to-purple-500/20 text-white border border-indigo-500/30'
                          : 'text-white/60 hover:text-white hover:bg-white/8',
                        collapsed && 'justify-center px-2',
                      )}
                    >
                      <item.icon className={clsx('flex-shrink-0 w-5 h-5', active ? 'text-indigo-400' : '')} />
                      {!collapsed && <span>{item.label}</span>}
                    </Link>
                  </li>
                )
              })}
            </ul>
          </div>
        ))}
      </nav>

      {/* Settings + User */}
      <div className="border-t border-white/10 p-3 space-y-1">
        <Link
          to="/settings"
          onClick={onClose}
          className={clsx(
            'flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm font-medium text-white/60 hover:text-white hover:bg-white/8 transition-all',
            collapsed && 'justify-center',
          )}
        >
          <Cog6ToothIcon className="w-5 h-5 flex-shrink-0" />
          {!collapsed && <span>Settings</span>}
        </Link>

        {!collapsed && user && (
          <div className="flex items-center gap-3 px-3 py-3 rounded-xl bg-white/5 border border-white/10">
            {user.avatar_url
              ? <img src={user.avatar_url} alt={user.full_name} className="w-8 h-8 rounded-full" />
              : <div className="w-8 h-8 rounded-full bg-gradient-to-br from-indigo-500 to-purple-600 flex items-center justify-center text-white text-xs font-bold">
                  {user.full_name?.[0] ?? 'U'}
                </div>
            }
            <div className="flex-1 min-w-0">
              <p className="text-sm font-medium text-white truncate">{user.full_name}</p>
              <p className="text-xs text-white/40 capitalize">{user.role}</p>
            </div>
            <button onClick={logout} className="text-white/40 hover:text-red-400 transition-colors" title="Logout">
              <ArrowRightOnRectangleIcon className="w-4 h-4" />
            </button>
          </div>
        )}
      </div>
    </div>
  )

  return (
    <>
      {/* Desktop sidebar */}
      <motion.aside
        animate={{ width: collapsed ? 64 : 240 }}
        transition={{ duration: 0.2, ease: 'easeInOut' }}
        className="hidden lg:flex flex-col h-screen sticky top-0 glass-card rounded-none border-r border-white/10 overflow-hidden"
      >
        <SidebarContent />
      </motion.aside>

      {/* Mobile overlay */}
      <AnimatePresence>
        {mobileOpen && (
          <>
            <motion.div
              initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
              className="lg:hidden fixed inset-0 z-40 bg-black/60 backdrop-blur-sm"
              onClick={onClose}
            />
            <motion.aside
              initial={{ x: -280 }} animate={{ x: 0 }} exit={{ x: -280 }}
              transition={{ type: 'spring', damping: 30, stiffness: 300 }}
              className="lg:hidden fixed inset-y-0 left-0 z-50 w-64 glass-card rounded-none border-r border-white/10"
            >
              <SidebarContent />
            </motion.aside>
          </>
        )}
      </AnimatePresence>
    </>
  )
}
