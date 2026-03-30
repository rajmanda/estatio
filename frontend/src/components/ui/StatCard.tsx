import { ReactNode } from 'react'
import { clsx } from 'clsx'
import { ArrowUpIcon, ArrowDownIcon } from '@heroicons/react/24/solid'
import { motion } from 'framer-motion'

interface StatCardProps {
  title: string
  value: string | number
  icon: ReactNode
  change?: number
  changeLabel?: string
  color?: 'indigo' | 'purple' | 'green' | 'amber' | 'red' | 'sky'
  prefix?: string
  suffix?: string
  className?: string
}

const colorMap = {
  indigo: 'from-indigo-500/20 to-indigo-600/10 border-indigo-500/20 text-indigo-400',
  purple: 'from-purple-500/20 to-purple-600/10 border-purple-500/20 text-purple-400',
  green:  'from-emerald-500/20 to-emerald-600/10 border-emerald-500/20 text-emerald-400',
  amber:  'from-amber-500/20 to-amber-600/10 border-amber-500/20 text-amber-400',
  red:    'from-red-500/20 to-red-600/10 border-red-500/20 text-red-400',
  sky:    'from-sky-500/20 to-sky-600/10 border-sky-500/20 text-sky-400',
}

export function StatCard({
  title, value, icon, change, changeLabel, color = 'indigo', prefix = '', suffix = '', className,
}: StatCardProps) {
  const isPositive = (change ?? 0) >= 0
  return (
    <motion.div
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      whileHover={{ y: -4, boxShadow: '0 16px 48px rgba(99,102,241,0.25)' }}
      transition={{ duration: 0.25 }}
      className={clsx(
        'glass-card p-6 bg-gradient-to-br border',
        colorMap[color],
        className,
      )}
    >
      <div className="flex items-start justify-between">
        <div className="flex-1">
          <p className="text-sm font-medium text-white/60 mb-1">{title}</p>
          <p className="text-3xl font-bold text-white tracking-tight">
            {prefix}{typeof value === 'number' ? value.toLocaleString() : value}{suffix}
          </p>
          {change !== undefined && (
            <div className="flex items-center gap-1 mt-2">
              {isPositive
                ? <ArrowUpIcon className="w-3 h-3 text-emerald-400" />
                : <ArrowDownIcon className="w-3 h-3 text-red-400" />}
              <span className={clsx('text-xs font-medium', isPositive ? 'text-emerald-400' : 'text-red-400')}>
                {Math.abs(change)}%
              </span>
              {changeLabel && <span className="text-xs text-white/40">{changeLabel}</span>}
            </div>
          )}
        </div>
        <div className={clsx('p-3 rounded-xl bg-white/5 border border-white/10', colorMap[color].split(' ').pop())}>
          {icon}
        </div>
      </div>
    </motion.div>
  )
}
