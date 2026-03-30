import { create } from 'zustand'
import { api } from '../services/api'

interface Notification {
  id: string
  type: string
  title: string
  message: string
  read: boolean
  action_url?: string
  priority: string
  created_at: string
}

interface NotificationState {
  notifications: Notification[]
  unreadCount: number
  loading: boolean
  fetchNotifications: () => Promise<void>
  fetchUnreadCount: () => Promise<void>
  markRead: (id: string) => Promise<void>
  markAllRead: () => Promise<void>
}

export const useNotificationStore = create<NotificationState>((set, get) => ({
  notifications: [],
  unreadCount: 0,
  loading: false,

  fetchNotifications: async () => {
    set({ loading: true })
    try {
      const res = await api.get('/notifications', { params: { limit: 50 } })
      set({ notifications: res.data.notifications, unreadCount: res.data.unread_count, loading: false })
    } catch {
      set({ loading: false })
    }
  },

  fetchUnreadCount: async () => {
    try {
      const res = await api.get('/notifications/unread-count')
      set({ unreadCount: res.data.unread_count })
    } catch {}
  },

  markRead: async (id: string) => {
    await api.post(`/notifications/${id}/read`)
    set(s => ({
      notifications: s.notifications.map(n => n.id === id ? { ...n, read: true } : n),
      unreadCount: Math.max(0, s.unreadCount - 1),
    }))
  },

  markAllRead: async () => {
    await api.post('/notifications/read-all')
    set(s => ({
      notifications: s.notifications.map(n => ({ ...n, read: true })),
      unreadCount: 0,
    }))
  },
}))
