import React from 'react'
import { motion, HTMLMotionProps } from 'framer-motion'
import { clsx } from 'clsx'
import { twMerge } from 'tailwind-merge'

type PaddingVariant = 'none' | 'sm' | 'md' | 'lg' | 'xl'

interface GlassCardProps extends Omit<HTMLMotionProps<'div'>, 'children'> {
  children: React.ReactNode
  className?: string
  hover?: boolean
  glow?: boolean
  glowColor?: 'primary' | 'success' | 'warning' | 'danger' | 'info'
  padding?: PaddingVariant
  animate?: boolean
  delay?: number
  heavy?: boolean
  interactive?: boolean
}

const paddingMap: Record<PaddingVariant, string> = {
  none: 'p-0',
  sm: 'p-3',
  md: 'p-5',
  lg: 'p-6',
  xl: 'p-8',
}

const glowColorMap: Record<string, string> = {
  primary: 'hover:shadow-[0_0_30px_rgba(99,102,241,0.35),0_12px_40px_rgba(99,102,241,0.25)]',
  success: 'hover:shadow-[0_0_30px_rgba(16,185,129,0.35),0_12px_40px_rgba(16,185,129,0.25)]',
  warning: 'hover:shadow-[0_0_30px_rgba(245,158,11,0.35),0_12px_40px_rgba(245,158,11,0.25)]',
  danger: 'hover:shadow-[0_0_30px_rgba(239,68,68,0.35),0_12px_40px_rgba(239,68,68,0.25)]',
  info: 'hover:shadow-[0_0_30px_rgba(59,130,246,0.35),0_12px_40px_rgba(59,130,246,0.25)]',
}

const cn = (...inputs: (string | undefined | null | false)[]) =>
  twMerge(clsx(inputs))

export const GlassCard: React.FC<GlassCardProps> = ({
  children,
  className,
  hover = false,
  glow = false,
  glowColor = 'primary',
  padding = 'lg',
  animate = true,
  delay = 0,
  heavy = false,
  interactive = false,
  ...motionProps
}) => {
  const baseClasses = cn(
    // Base glass morphism
    'relative overflow-hidden rounded-2xl',
    'border border-white/[0.12]',
    heavy
      ? 'backdrop-blur-[40px] bg-white/[0.05]'
      : 'backdrop-blur-[20px] bg-white/[0.08]',
    'shadow-glass',
    // Inner highlight
    'before:absolute before:inset-0 before:rounded-2xl before:pointer-events-none',
    'before:bg-gradient-to-br before:from-white/[0.06] before:to-transparent',
    // Padding
    paddingMap[padding],
    // Hover effects
    hover && [
      'transition-all duration-300 cursor-pointer',
      'hover:bg-white/[0.12] hover:border-white/[0.22]',
      'hover:-translate-y-1 hover:shadow-glass-hover',
    ],
    // Interactive (button-like)
    interactive && 'cursor-pointer active:scale-[0.98] active:translate-y-0',
    // Glow on hover
    glow && hover && glowColorMap[glowColor],
    className
  )

  if (!animate) {
    return (
      <div className={baseClasses} {...(motionProps as React.HTMLAttributes<HTMLDivElement>)}>
        {children}
      </div>
    )
  }

  return (
    <motion.div
      className={baseClasses}
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{
        duration: 0.45,
        delay,
        ease: [0.22, 1, 0.36, 1],
      }}
      {...motionProps}
    >
      {children}
    </motion.div>
  )
}

/* ── Convenience sub-components ─────────────────────────────────────────────── */

export const GlassCardHeader: React.FC<{
  children: React.ReactNode
  className?: string
  divider?: boolean
}> = ({ children, className, divider = true }) => (
  <div
    className={cn(
      'flex items-center justify-between',
      divider && 'pb-4 mb-4 border-b border-white/[0.07]',
      className
    )}
  >
    {children}
  </div>
)

export const GlassCardTitle: React.FC<{
  children: React.ReactNode
  className?: string
  subtitle?: string
}> = ({ children, className, subtitle }) => (
  <div className={className}>
    <h3 className="text-base font-semibold text-white/90 leading-tight">{children}</h3>
    {subtitle && <p className="text-xs text-white/45 mt-0.5">{subtitle}</p>}
  </div>
)

export const GlassCardBody: React.FC<{
  children: React.ReactNode
  className?: string
}> = ({ children, className }) => (
  <div className={cn('flex-1', className)}>{children}</div>
)

export const GlassCardFooter: React.FC<{
  children: React.ReactNode
  className?: string
}> = ({ children, className }) => (
  <div
    className={cn(
      'pt-4 mt-4 border-t border-white/[0.07] flex items-center justify-between',
      className
    )}
  >
    {children}
  </div>
)

export default GlassCard
