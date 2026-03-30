import axios from 'axios'

const BASE_URL = `${import.meta.env.VITE_API_URL ?? ''}/api/v1`

export const api = axios.create({
  baseURL: BASE_URL,
  headers: { 'Content-Type': 'application/json' },
})

// Inject JWT on every request
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('access_token')
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

// Handle 401 — redirect to login
api.interceptors.response.use(
  (res) => res,
  async (error) => {
    const original = error.config
    if (error.response?.status === 401 && !original._retry) {
      original._retry = true
      const refresh = localStorage.getItem('refresh_token')
      if (refresh) {
        try {
          const res = await axios.post(`${BASE_URL}/auth/token`, { refresh_token: refresh })
          const { access_token, refresh_token } = res.data
          localStorage.setItem('access_token', access_token)
          localStorage.setItem('refresh_token', refresh_token)
          original.headers.Authorization = `Bearer ${access_token}`
          return api(original)
        } catch {
          localStorage.removeItem('access_token')
          localStorage.removeItem('refresh_token')
          window.location.href = '/login'
        }
      } else {
        window.location.href = '/login'
      }
    }
    return Promise.reject(error)
  }
)

// ── Typed API helpers ──────────────────────────────────────────────────────────

export const authApi = {
  getMe:   () => api.get('/auth/me'),
  logout:  () => api.post('/auth/logout'),
}

export const propertiesApi = {
  list:           (params?: object) => api.get('/properties', { params }),
  get:            (id: string)      => api.get(`/properties/${id}`),
  create:         (data: object)    => api.post('/properties', data),
  update:         (id: string, data: object) => api.put(`/properties/${id}`, data),
  delete:         (id: string)      => api.delete(`/properties/${id}`),
  getFinancials:  (id: string)      => api.get(`/properties/${id}/financials`),
  getOwners:      (id: string)      => api.get(`/properties/${id}/owners`),
  assignOwner:    (id: string, data: object) => api.post(`/properties/${id}/owners`, data),
  removeOwner:    (id: string, ownerId: string) => api.delete(`/properties/${id}/owners/${ownerId}`),
}

export const ownersApi = {
  list:         (params?: object) => api.get('/owners', { params }),
  get:          (id: string)      => api.get(`/owners/${id}`),
  getPortfolio: (id: string)      => api.get(`/owners/${id}/portfolio`),
  getDashboard: (id: string)      => api.get(`/owners/${id}/dashboard`),
  getInvoices:  (id: string, params?: object) => api.get(`/owners/${id}/invoices`, { params }),
  getPayments:  (id: string, params?: object) => api.get(`/owners/${id}/payments`, { params }),
  getMaintenance: (id: string)    => api.get(`/owners/${id}/maintenance`),
  getStatements:  (id: string)    => api.get(`/owners/${id}/statements`),
}

export const accountingApi = {
  getAccounts:      (params?: object) => api.get('/accounting/accounts', { params }),
  createAccount:    (data: object)    => api.post('/accounting/accounts', data),
  createEntry:      (data: object)    => api.post('/accounting/journal-entries', data),
  getEntries:       (params?: object) => api.get('/accounting/journal-entries', { params }),
  voidEntry:        (id: string, reason: string) => api.post(`/accounting/journal-entries/${id}/void`, { reason }),
  getTrialBalance:  (params?: object) => api.get('/accounting/reports/trial-balance', { params }),
  getIncomeStatement: (params?: object) => api.get('/accounting/reports/income-statement', { params }),
  getBalanceSheet:  (params?: object) => api.get('/accounting/reports/balance-sheet', { params }),
  getCashFlow:      (params?: object) => api.get('/accounting/reports/cash-flow', { params }),
  getOwnerStatement: (ownerId: string, params?: object) => api.get(`/accounting/reports/owner-statement/${ownerId}`, { params }),
}

export const maintenanceApi = {
  list:           (params?: object) => api.get('/maintenance', { params }),
  get:            (id: string)      => api.get(`/maintenance/${id}`),
  create:         (data: object)    => api.post('/maintenance', data),
  updateStatus:   (id: string, data: object) => api.post(`/maintenance/${id}/status`, data),
  submitEstimate: (id: string, data: object) => api.post(`/maintenance/${id}/estimates`, data),
  selectEstimate: (id: string, data: object) => api.post(`/maintenance/${id}/select-estimate`, data),
  approve:        (id: string, data: object) => api.post(`/maintenance/${id}/approve`, data),
  complete:       (id: string, data: object) => api.post(`/maintenance/${id}/complete`, data),
  getSummary:     (params?: object) => api.get('/maintenance/summary', { params }),
  getPreventive:  () => api.get('/maintenance/preventive/schedules'),
  createPreventive: (data: object) => api.post('/maintenance/preventive/schedules', data),
}

export const vendorsApi = {
  list:       (params?: object) => api.get('/vendors', { params }),
  get:        (id: string)      => api.get(`/vendors/${id}`),
  create:     (data: object)    => api.post('/vendors', data),
  update:     (id: string, data: object) => api.put(`/vendors/${id}`, data),
  getInvoices: (id: string)     => api.get(`/vendors/${id}/invoices`),
  createInvoice: (id: string, data: object) => api.post(`/vendors/${id}/invoices`, data),
  getWorkOrders: (id: string)   => api.get(`/vendors/${id}/work-orders`),
  getStats:   (id: string)      => api.get(`/vendors/${id}/stats`),
}

export const documentsApi = {
  upload:       (formData: FormData) => api.post('/documents/upload', formData, { headers: { 'Content-Type': 'multipart/form-data' } }),
  list:         (params?: object) => api.get('/documents', { params }),
  get:          (id: string)      => api.get(`/documents/${id}`),
  getSignedUrl: (id: string)      => api.get(`/documents/${id}/download`),
  delete:       (id: string)      => api.delete(`/documents/${id}`),
  reprocess:    (id: string)      => api.post(`/documents/${id}/reprocess`),
}

export const notificationsApi = {
  list:        (params?: object) => api.get('/notifications', { params }),
  unreadCount: ()                => api.get('/notifications/unread-count'),
  markRead:    (id: string)      => api.post(`/notifications/${id}/read`),
  markAllRead: ()                => api.post('/notifications/read-all'),
  delete:      (id: string)      => api.delete(`/notifications/${id}`),
}

export const aiApi = {
  query:       (query: string)   => api.post('/ai/query', { query }),
  insights:    (propertyId: string) => api.get(`/ai/insights/${propertyId}`),
  predictions: (propertyId: string) => api.get(`/ai/predict/${propertyId}`),
  reclassify:  (docId: string)   => api.post(`/ai/documents/${docId}/classify`),
}
