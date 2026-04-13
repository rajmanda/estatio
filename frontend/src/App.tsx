import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { lazy, Suspense } from 'react'
import { AppLayout } from './components/layout/AppLayout'
import { useAuthStore } from './store/authStore'
import LoginPage from './pages/auth/LoginPage'
import AuthCallback from './pages/auth/AuthCallback'

const qc = new QueryClient({
  defaultOptions: { queries: { staleTime: 30_000, retry: 1 } },
})

// Lazy-load all pages
const OwnerDashboard   = lazy(() => import('./pages/dashboard/OwnerDashboard'))
const AdminDashboard   = lazy(() => import('./pages/dashboard/AdminDashboard'))
const PropertiesPage   = lazy(() => import('./pages/properties/PropertiesPage'))
const MaintenancePage  = lazy(() => import('./pages/maintenance/MaintenancePage'))
const NotificationsPage = lazy(() => import('./pages/notifications/NotificationsPage'))
const AISearch         = lazy(() => import('./pages/ai/AISearch'))
const OwnersPage       = lazy(() => import('./pages/owners/OwnersPage'))
const TenantsPage      = lazy(() => import('./pages/tenants/TenantsPage'))
const AccountingPage   = lazy(() => import('./pages/accounting/AccountingPage'))
const InvoicesPage     = lazy(() => import('./pages/invoices/InvoicesPage'))
const VendorsPage      = lazy(() => import('./pages/vendors/VendorsPage'))
const DocumentsPage    = lazy(() => import('./pages/documents/DocumentsPage'))
const SettingsPage     = lazy(() => import('./pages/settings/SettingsPage'))
const AddPropertyPage  = lazy(() => import('./pages/properties/AddPropertyPage'))

const Spinner = () => (
  <div className="flex items-center justify-center h-64">
    <div className="w-8 h-8 border-2 border-indigo-500 border-t-transparent rounded-full animate-spin" />
  </div>
)

function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const { isAuthenticated } = useAuthStore()
  if (!isAuthenticated) return <Navigate to="/login" replace />
  return <>{children}</>
}

function DashboardRoute() {
  const { user } = useAuthStore()
  return user?.role === 'admin' || user?.role === 'manager'
    ? <AdminDashboard />
    : <OwnerDashboard />
}

export default function App() {
  return (
    <QueryClientProvider client={qc}>
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route path="/auth/callback" element={<AuthCallback />} />
          <Route
            path="/"
            element={
              <ProtectedRoute>
                <AppLayout />
              </ProtectedRoute>
            }
          >
            <Route index element={<Navigate to="/dashboard" replace />} />
            <Route path="dashboard" element={<Suspense fallback={<Spinner />}><DashboardRoute /></Suspense>} />
            <Route path="properties/new" element={<Suspense fallback={<Spinner />}><AddPropertyPage /></Suspense>} />
            <Route path="properties" element={<Suspense fallback={<Spinner />}><PropertiesPage /></Suspense>} />
            <Route path="maintenance" element={<Suspense fallback={<Spinner />}><MaintenancePage /></Suspense>} />
            <Route path="notifications" element={<Suspense fallback={<Spinner />}><NotificationsPage /></Suspense>} />
            <Route path="ai-search" element={<Suspense fallback={<Spinner />}><AISearch /></Suspense>} />
            <Route path="owners"      element={<Suspense fallback={<Spinner />}><OwnersPage /></Suspense>} />
            <Route path="tenants"     element={<Suspense fallback={<Spinner />}><TenantsPage /></Suspense>} />
            <Route path="accounting"  element={<Suspense fallback={<Spinner />}><AccountingPage /></Suspense>} />
            <Route path="invoices"    element={<Suspense fallback={<Spinner />}><InvoicesPage /></Suspense>} />
            <Route path="vendors"     element={<Suspense fallback={<Spinner />}><VendorsPage /></Suspense>} />
            <Route path="documents"   element={<Suspense fallback={<Spinner />}><DocumentsPage /></Suspense>} />
            <Route path="settings"    element={<Suspense fallback={<Spinner />}><SettingsPage /></Suspense>} />
            <Route path="*"           element={<Navigate to="/dashboard" replace />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  )
}

function ComingSoon({ title }: { title: string }) {
  return (
    <div className="flex items-center justify-center h-64 text-center">
      <div>
        <div className="w-16 h-16 rounded-2xl bg-gradient-to-br from-indigo-500/20 to-purple-600/20 border border-white/10 flex items-center justify-center mx-auto mb-4">
          <span className="text-2xl">🚧</span>
        </div>
        <h3 className="text-lg font-semibold text-white">{title}</h3>
        <p className="text-white/40 text-sm mt-1">Coming soon in the next sprint</p>
      </div>
    </div>
  )
}
