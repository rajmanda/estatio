import React from 'react'
import { clsx } from 'clsx'
import { twMerge } from 'tailwind-merge'
import {
  CheckCircleIcon,
  ClockIcon,
  ExclamationCircleIcon,
  MinusCircleIcon,
  BoltIcon,
  XCircleIcon,
  ArrowPathIcon,
  PauseCircleIcon,
} from '@heroicons/react/24/solid'

const cn = (...inputs: Parameters<typeof clsx>) => twMerge(clsx(inputs))

export type BadgeStatus =
  | 'paid'
  | 'active'
  | 'pending'
  | 'overdue'
  | 'urgent'
  | 'draft'
  | 'cancelled'
  | 'completed'
  | 'in_progress'
  | 'approved'
  | 'rejected'
  | 'sent'
  | 'open'
  | 'closed'
  | 'on_hold'
  | 'new'
  | 'inactive'
  | 'past'
  | 'eviction'
  | 'void'

export type BadgeVariant = 'filled' | 'soft' | 'outline' | 'dot'
export type BadgeSize = 'xs' | 'sm' | 'md' | 'lg'

interface GlassBadgeProps {
  status?: BadgeStatus
  variant?: BadgeVariant
  size?: BadgeSize
  label?: string
  icon?: boolean
  pulse?: boolean
  className?: string
  children?: React.ReactNode
}

const statusConfig: Record<
  BadgeStatus,
  {
    label: string
    color: string
    bg: string
    border: string
    dot: string
    icon: React.ComponentType<React.SVGProps<SVGSVGElement>>
    glow?: string
  }
> = {
  paid: {
    label: 'Paid',
    color: 'text-emerald-300',
    bg: 'bg-emerald-500/[0.15]',
    border: 'border-emerald-500/30',
    dot: 'bg-emerald-400',
    icon: CheckCircleIcon,
    glow: 'shadow-[0_0_12px_rgba(16,185,129,0.25)]',
  },
  active: {
    label: 'Active',
    color: 'text-emerald-300',
    bg: 'bg-emerald-500/[0.15]',
    border: 'border-emerald-500/30',
    dot: 'bg-emerald-400',
    icon: CheckCircleIcon,
    glow: 'shadow-[0_0_12px_rgba(16,185,129,0.25)]',
  },
  completed: {
    label: 'Completed',
    color: 'text-emerald-300',
    bg: 'bg-emerald-500/[0.15]',
    border: 'border-emerald-500/30',
    dot: 'bg-emerald-400',
    icon: CheckCircleIcon,
  },
  approved: {
    label: 'Approved',
    color: 'text-emerald-300',
    bg: 'bg-emerald-500/[0.15]',
    border: 'border-emerald-500/30',
    dot: 'bg-emerald-400',
    icon: CheckCircleIcon,
  },
  closed: {
    label: 'Closed',
    color: 'text-emerald-300',
    bg: 'bg-emerald-500/[0.12]',
    border: 'border-emerald-500/25',
    dot: 'bg-emerald-500',
    icon: CheckCircleIcon,
  },
  pending: {
    label: 'Pending',
    color: 'text-amber-300',
    bg: 'bg-amber-500/[0.15]',
    border: 'border-amber-500/30',
    dot: 'bg-amber-400',
    icon: ClockIcon,
    glow: 'shadow-[0_0_12px_rgba(245,158,11,0.2)]',
  },
  sent: {
    label: 'Sent',
    color: 'text-blue-300',
    bg: 'bg-blue-500/[0.15]',
    border: 'border-blue-500/30',
    dot: 'bg-blue-400',
    icon: ClockIcon,
  },
  on_hold: {
    label: 'On Hold',
    color: 'text-amber-300',
    bg: 'bg-amber-500/[0.12]',
    border: 'border-amber-500/25',
    dot: 'bg-amber-400',
    icon: PauseCircleIcon,
  },
  in_progress: {
    label: 'In Progress',
    color: 'text-blue-300',
    bg: 'bg-blue-500/[0.15]',
    border: 'border-blue-500/30',
    dot: 'bg-blue-400',
    icon: ArrowPathIcon,
  },
  open: {
    label: 'Open',
    color: 'text-sky-300',
    bg: 'bg-sky-500/[0.15]',
    border: 'border-sky-500/30',
    dot: 'bg-sky-400',
    icon: BoltIcon,
  },
  new: {
    label: 'New',
    color: 'text-violet-300',
    bg: 'bg-violet-500/[0.15]',
    border: 'border-violet-500/30',
    dot: 'bg-violet-400',
    icon: BoltIcon,
  },
  overdue: {
    label: 'Overdue',
    color: 'text-red-300',
    bg: 'bg-red-500/[0.15]',
    border: 'border-red-500/30',
    dot: 'bg-red-400',
    icon: ExclamationCircleIcon,
    glow: 'shadow-[0_0_12px_rgba(239,68,68,0.25)]',
  },
  urgent: {
    label: 'Urgent',
    color: 'text-red-300',
    bg: 'bg-red-500/[0.15]',
    border: 'border-red-500/30',
    dot: 'bg-red-400',
    icon: ExclamationCircleIcon,
    glow: 'shadow-[0_0_12px_rgba(239,68,68,0.25)]',
  },
  rejected: {
    label: 'Rejected',
    color: 'text-red-300',
    bg: 'bg-red-500/[0.12]',
    border: 'border-red-500/25',
    dot: 'bg-red-400',
    icon: XCircleIcon,
  },
  draft: {
    label: 'Draft',
    color: 'text-white/50',
    bg: 'bg-white/[0.06]',
    border: 'border-white/[0.12]',
    dot: 'bg-white/40',
    icon: MinusCircleIcon,
  },
  cancelled: {
    label: 'Cancelled',
    color: 'text-white/40',
    bg: 'bg-white/[0.05]',
    border: 'border-white/[0.1]',
    dot: 'bg-white/30',
    icon: XCircleIcon,
  },
  inactive: {
    label: 'Inactive',
    color: 'text-white/40',
    bg: 'bg-white/[0.05]',
    border: 'border-white/[0.1]',
    dot: 'bg-white/30',
    icon: MinusCircleIcon,
  },
  past: {
    label: 'Past',
    color: 'text-white/40',
    bg: 'bg-white/[0.05]',
    border: 'border-white/[0.1]',
    dot: 'bg-white/30',
    icon: MinusCircleIcon,
  },
  eviction: {
    label: 'Eviction',
    color: 'text-red-300',
    bg: 'bg-red-500/[0.15]',
    border: 'border-red-500/30',
    dot: 'bg-red-400',
    icon: ExclamationCircleIcon,
    glow: 'shadow-[0_0_12px_rgba(239,68,68,0.25)]',
  },
  void: {
    label: 'Void',
    color: 'text-white/40',
    bg: 'bg-white/[0.05]',
    border: 'border-white/[0.1]',
    dot: 'bg-white/30',
    icon: XCircleIcon,
  },
}

const sizeClasses: Record<BadgeSize, string> = {
  xs: 'text-[10px] px-1.5 py-0.5 gap-1 rounded-md',
  sm: 'text-xs px-2 py-0.5 gap-1 rounded-lg',
  md: 'text-xs px-2.5 py-1 gap-1.5 rounded-lg',
  lg: 'text-sm px-3 py-1.5 gap-2 rounded-xl',
}

const dotSizeClasses: Record<BadgeSize, string> = {
  xs: 'w-1.5 h-1.5',
  sm: 'w-1.5 h-1.5',
  md: 'w-2 h-2',
  lg: 'w-2.5 h-2.5',
}

const iconSizeClasses: Record<BadgeSize, string> = {
  xs: 'w-2.5 h-2.5',
  sm: 'w-3 h-3',
  md: 'w-3.5 h-3.5',
  lg: 'w-4 h-4',
}

export const GlassBadge: React.FC<GlassBadgeProps> = ({
  status = 'draft',
  variant = 'soft',
  size = 'md',
  label,
  icon = false,
  pulse = false,
  className,
  children,
}) => {
  const config = statusConfig[status]
  const displayLabel = label ?? children ?? config.label
  const IconComponent = config.icon

  const isOverdue = status === 'overdue' || status === 'urgent'
  const isPending = status === 'pending' || status === 'in_progress'

  return (
    <span
      className={cn(
        'inline-flex items-center font-medium tracking-wide whitespace-nowrap',
        sizeClasses[size],
        // Variant styles
        variant === 'soft' || variant === 'filled'
          ? [config.bg, config.color, 'border', config.border]
          : variant === 'outline'
          ? ['bg-transparent', config.color, 'border', config.border]
          : ['bg-transparent', config.color],
        // Glow effect for important statuses
        (variant === 'soft' || variant === 'filled') && config.glow,
        // Glass backdrop
        'backdrop-blur-[8px]',
        className
      )}
    >
      {/* Dot or icon */}
      {icon ? (
        <IconComponent className={cn(iconSizeClasses[size], 'shrink-0')} />
      ) : (
        <span
          className={cn(
            dotSizeClasses[size],
            'rounded-full shrink-0 flex-none',
            config.dot,
            pulse && isOverdue && 'animate-pulse',
            pulse && isPending && 'animate-pulse opacity-80'
          )}
        />
      )}

      {displayLabel}
    </span>
  )
}

/* ── Number / count badge ───────────────────────────────────────────────────── */
interface CountBadgeProps {
  count: number
  max?: number
  color?: 'primary' | 'danger' | 'warning' | 'success'
  size?: 'sm' | 'md'
  className?: string
}

const countColorMap = {
  primary: 'bg-indigo-500 text-white shadow-[0_0_8px_rgba(99,102,241,0.5)]',
  danger: 'bg-red-500 text-white shadow-[0_0_8px_rgba(239,68,68,0.5)]',
  warning: 'bg-amber-500 text-white shadow-[0_0_8px_rgba(245,158,11,0.5)]',
  success: 'bg-emerald-500 text-white shadow-[0_0_8px_rgba(16,185,129,0.5)]',
}

export const CountBadge: React.FC<CountBadgeProps> = ({
  count,
  max = 99,
  color = 'danger',
  size = 'sm',
  className,
}) => {
  if (count <= 0) return null

  const displayCount = count > max ? `${max}+` : String(count)

  return (
    <span
      className={cn(
        'inline-flex items-center justify-center font-bold rounded-full',
        size === 'sm' ? 'min-w-[18px] h-[18px] text-[10px] px-1' : 'min-w-[22px] h-[22px] text-xs px-1.5',
        countColorMap[color],
        className
      )}
    >
      {displayCount}
    </span>
  )
}

export default GlassBadge
