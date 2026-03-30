import { useEffect } from 'react'
import { motion } from 'framer-motion'
import { BellIcon, CheckIcon } from '@heroicons/react/24/outline'
import { GlassCard } from '../../components/ui/GlassCard'
import { GlassButton } from '../../components/ui/GlassButton'
import { useNotificationStore } from '../../store/notificationStore'
import { formatDistanceToNow } from 'date-fns'

const TYPE_ICON: Record<string, string> = {
  invoice_created: '📄', invoice_due: '⚠️', invoice_overdue: '🔴', payment_received: '✅',
  maintenance_submitted: '🔧', maintenance_updated: '🔧', maintenance_completed: '✅',
  lease_expiring: '📅', hoa_deadline: '🏛️', ai_insight: '🤖', system: '⚙️',
}

export default function NotificationsPage() {
  const { notifications, loading, fetchNotifications, markRead, markAllRead, unreadCount } = useNotificationStore()

  useEffect(() => { fetchNotifications() }, [])

  return (
    <div className="max-w-2xl mx-auto space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-bold text-white">Notifications</h2>
          {unreadCount > 0 && <p className="text-white/40 text-sm mt-0.5">{unreadCount} unread</p>}
        </div>
        {unreadCount > 0 && (
          <GlassButton onClick={markAllRead} icon={<CheckIcon className="w-4 h-4" />} variant="secondary">
            Mark all read
          </GlassButton>
        )}
      </div>

      {loading ? (
        <div className="flex items-center justify-center h-48">
          <div className="w-8 h-8 border-2 border-indigo-500 border-t-transparent rounded-full animate-spin" />
        </div>
      ) : notifications.length === 0 ? (
        <div className="text-center py-16 text-white/30">
          <BellIcon className="w-12 h-12 mx-auto mb-3 opacity-30" />
          <p>No notifications</p>
        </div>
      ) : (
        <div className="space-y-2">
          {notifications.map((n, i) => (
            <motion.div key={n.id} initial={{ opacity: 0, x: -8 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: i * 0.03 }}>
              <GlassCard
                hover
                className={`cursor-pointer ${!n.read ? 'border-indigo-500/20' : ''}`}
                onClick={() => !n.read && markRead(n.id)}
              >
                <div className="flex items-start gap-3">
                  <span className="text-xl flex-shrink-0">{TYPE_ICON[n.type] ?? '🔔'}</span>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-start justify-between gap-2">
                      <p className={`text-sm font-medium ${n.read ? 'text-white/70' : 'text-white'}`}>{n.title}</p>
                      <span className="text-xs text-white/30 flex-shrink-0 whitespace-nowrap">
                        {formatDistanceToNow(new Date(n.created_at), { addSuffix: true })}
                      </span>
                    </div>
                    <p className="text-sm text-white/50 mt-0.5">{n.message}</p>
                  </div>
                  {!n.read && <div className="w-2 h-2 rounded-full bg-indigo-400 flex-shrink-0 mt-1.5" />}
                </div>
              </GlassCard>
            </motion.div>
          ))}
        </div>
      )}
    </div>
  )
}
