import React from 'react'
import { motion, HTMLMotionProps } from 'framer-motion'
import { clsx } from 'clsx'
import { twMerge } from 'tailwind-merge'

type ButtonVariant = 'primary' | 'secondary' | 'danger' | 'success' | 'warning' | 'ghost'
type ButtonSize = 'xs' | 'sm' | 'md' | 'lg' | 'xl'

interface GlassButtonProps extends Omit<HTMLMotionProps<'button'>, 'children'> {
  children?: React.ReactNode
  variant?: ButtonVariant
  size?: ButtonSize
  loading?: boolean
  icon?: React.ReactNode
  iconPosition?: 'left' | 'right'
  fullWidth?: boolean
  rounded?: boolean
  disabled?: boolean
  className?: string
}

const cn = (...inputs: Parameters<typeof clsx>) => twMerge(clsx(inputs))

const variantClasses: Record<ButtonVariant, string> = {
  primary: [
    'bg-gradient-to-r from-indigo-500 to-purple-600',
    'border border-indigo-400/50',
    'text-white',
    'shadow-[0_4px_16px_rgba(99,102,241,0.35),inset_0_1px_0_rgba(255,255,255,0.2)]',
    'hover:shadow-[0_8px_24px_rgba(99,102,241,0.55),inset_0_1px_0_rgba(255,255,255,0.2)]',
    'hover:from-indigo-400 hover:to-purple-500',
    'active:shadow-[0_4px_12px_rgba(99,102,241,0.3)]',
  ].join(' '),

  secondary: [
    'backdrop-blur-[10px]',
    'bg-white/[0.08]',
    'border border-white/[0.18]',
    'text-white/80',
    'shadow-[0_4px_16px_rgba(0,0,0,0.2),inset_0_1px_0_rgba(255,255,255,0.08)]',
    'hover:bg-white/[0.14] hover:border-white/[0.3] hover:text-white',
    'hover:shadow-[0_8px_24px_rgba(0,0,0,0.3)]',
  ].join(' '),

  danger: [
    'bg-gradient-to-r from-red-500 to-rose-600',
    'border border-red-400/50',
    'text-white',
    'shadow-[0_4px_16px_rgba(239,68,68,0.35),inset_0_1px_0_rgba(255,255,255,0.2)]',
    'hover:shadow-[0_8px_24px_rgba(239,68,68,0.55)]',
    'hover:from-red-400 hover:to-rose-500',
  ].join(' '),

  success: [
    'bg-gradient-to-r from-emerald-500 to-teal-600',
    'border border-emerald-400/50',
    'text-white',
    'shadow-[0_4px_16px_rgba(16,185,129,0.35),inset_0_1px_0_rgba(255,255,255,0.2)]',
    'hover:shadow-[0_8px_24px_rgba(16,185,129,0.55)]',
    'hover:from-emerald-400 hover:to-teal-500',
  ].join(' '),

  warning: [
    'bg-gradient-to-r from-amber-500 to-orange-600',
    'border border-amber-400/50',
    'text-white',
    'shadow-[0_4px_16px_rgba(245,158,11,0.35),inset_0_1px_0_rgba(255,255,255,0.2)]',
    'hover:shadow-[0_8px_24px_rgba(245,158,11,0.55)]',
  ].join(' '),

  ghost: [
    'bg-transparent',
    'border border-transparent',
    'text-white/60',
    'hover:bg-white/[0.06] hover:text-white/90 hover:border-white/[0.1]',
  ].join(' '),
}

const sizeClasses: Record<ButtonSize, string> = {
  xs: 'px-2.5 py-1.5 text-xs gap-1.5 rounded-lg',
  sm: 'px-3.5 py-2 text-sm gap-2 rounded-xl',
  md: 'px-5 py-2.5 text-sm gap-2 rounded-xl',
  lg: 'px-6 py-3 text-base gap-2.5 rounded-2xl',
  xl: 'px-8 py-4 text-base gap-3 rounded-2xl',
}

/* Spinner component */
const Spinner: React.FC<{ size?: 'sm' | 'md' }> = ({ size = 'sm' }) => (
  <svg
    className={cn(
      'animate-spin',
      size === 'sm' ? 'w-3.5 h-3.5' : 'w-4 h-4'
    )}
    fill="none"
    viewBox="0 0 24 24"
  >
    <circle
      className="opacity-25"
      cx="12"
      cy="12"
      r="10"
      stroke="currentColor"
      strokeWidth="4"
    />
    <path
      className="opacity-75"
      fill="currentColor"
      d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
    />
  </svg>
)

export const GlassButton: React.FC<GlassButtonProps> = ({
  children,
  variant = 'secondary',
  size = 'md',
  loading = false,
  icon,
  iconPosition = 'left',
  fullWidth = false,
  rounded = false,
  disabled = false,
  className,
  ...motionProps
}) => {
  const isDisabled = disabled || loading

  return (
    <motion.button
      className={cn(
        'inline-flex items-center justify-center font-medium',
        'transition-all duration-200',
        'focus:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500/50 focus-visible:ring-offset-1 focus-visible:ring-offset-transparent',
        sizeClasses[size],
        variantClasses[variant],
        rounded && '!rounded-full',
        fullWidth && 'w-full',
        isDisabled && 'opacity-50 cursor-not-allowed pointer-events-none',
        className
      )}
      disabled={isDisabled}
      whileHover={isDisabled ? {} : { scale: 1.02, y: -1 }}
      whileTap={isDisabled ? {} : { scale: 0.97, y: 0 }}
      transition={{ duration: 0.15, ease: 'easeOut' }}
      {...motionProps}
    >
      {/* Left icon / spinner */}
      {loading ? (
        <Spinner size={size === 'xs' || size === 'sm' ? 'sm' : 'md'} />
      ) : (
        icon && iconPosition === 'left' && (
          <span className="shrink-0 flex items-center">{icon}</span>
        )
      )}

      {/* Label */}
      {children && (
        <span className={cn(loading && 'opacity-70')}>{children}</span>
      )}

      {/* Right icon */}
      {!loading && icon && iconPosition === 'right' && (
        <span className="shrink-0 flex items-center">{icon}</span>
      )}
    </motion.button>
  )
}

/* ── Icon-only button ───────────────────────────────────────────────────────── */
interface IconButtonProps extends Omit<GlassButtonProps, 'icon' | 'iconPosition'> {
  icon: React.ReactNode
  label: string
}

export const GlassIconButton: React.FC<IconButtonProps> = ({
  icon,
  label,
  size = 'md',
  variant = 'secondary',
  className,
  ...props
}) => {
  const iconSizeMap: Record<ButtonSize, string> = {
    xs: 'p-1.5 rounded-lg',
    sm: 'p-2 rounded-xl',
    md: 'p-2.5 rounded-xl',
    lg: 'p-3 rounded-2xl',
    xl: 'p-3.5 rounded-2xl',
  }

  return (
    <GlassButton
      variant={variant}
      aria-label={label}
      className={cn(iconSizeMap[size], 'aspect-square', className)}
      {...props}
    >
      {icon}
    </GlassButton>
  )
}

export default GlassButton
