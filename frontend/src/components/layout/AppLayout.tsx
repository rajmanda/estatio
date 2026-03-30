import { useState } from 'react'
import { Outlet, useLocation } from 'react-router-dom'
import { Sidebar } from './Sidebar'
import { Header } from './Header'

const pageTitles: Record<string, string> = {
  '/dashboard':    'Dashboard',
  '/properties':   'Properties',
  '/owners':       'Owners',
  '/tenants':      'Tenants',
  '/accounting':   'Accounting',
  '/invoices':     'Invoices',
  '/maintenance':  'Maintenance',
  '/vendors':      'Vendors',
  '/documents':    'Documents',
  '/notifications':'Notifications',
  '/ai-search':    'AI Search',
  '/settings':     'Settings',
}

export function AppLayout() {
  const [mobileSidebarOpen, setMobileSidebarOpen] = useState(false)
  const location = useLocation()

  const title = Object.entries(pageTitles).find(
    ([path]) => location.pathname.startsWith(path)
  )?.[1] ?? 'Estatio'

  return (
    <div className="flex h-screen overflow-hidden bg-[radial-gradient(ellipse_at_top_left,_var(--tw-gradient-stops))] from-slate-900 via-[#0f0c29] to-[#1a1035]">
      <Sidebar mobileOpen={mobileSidebarOpen} onClose={() => setMobileSidebarOpen(false)} />
      <div className="flex flex-col flex-1 min-w-0 overflow-hidden">
        <Header title={title} onMenuClick={() => setMobileSidebarOpen(true)} />
        <main className="flex-1 overflow-y-auto p-4 lg:p-6">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
