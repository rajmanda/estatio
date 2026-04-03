import React, { forwardRef, useState } from 'react'
import { clsx } from 'clsx'
import { twMerge } from 'tailwind-merge'
import { EyeIcon, EyeSlashIcon, ExclamationCircleIcon } from '@heroicons/react/24/outline'
import { motion, AnimatePresence } from 'framer-motion'

const cn = (...inputs: Parameters<typeof clsx>) => twMerge(clsx(inputs))

interface GlassInputProps extends Omit<React.InputHTMLAttributes<HTMLInputElement>, 'size'> {
  label?: string
  error?: string
  hint?: string
  icon?: React.ReactNode
  iconPosition?: 'left' | 'right'
  suffix?: React.ReactNode
  size?: 'sm' | 'md' | 'lg'
  fullWidth?: boolean
  containerClassName?: string
  labelClassName?: string
}

const sizeMap = {
  sm: {
    input: 'py-2 text-sm',
    paddingLeft: 'pl-3',
    paddingLeftWithIcon: 'pl-9',
    paddingRight: 'pr-3',
    paddingRightWithIcon: 'pr-9',
    label: 'text-xs',
    icon: 'w-4 h-4',
  },
  md: {
    input: 'py-2.5 text-sm',
    paddingLeft: 'pl-4',
    paddingLeftWithIcon: 'pl-10',
    paddingRight: 'pr-4',
    paddingRightWithIcon: 'pr-10',
    label: 'text-sm',
    icon: 'w-4 h-4',
  },
  lg: {
    input: 'py-3.5 text-base',
    paddingLeft: 'pl-5',
    paddingLeftWithIcon: 'pl-12',
    paddingRight: 'pr-5',
    paddingRightWithIcon: 'pr-12',
    label: 'text-sm',
    icon: 'w-5 h-5',
  },
}

export const GlassInput = forwardRef<HTMLInputElement, GlassInputProps>(
  (
    {
      label,
      error,
      hint,
      icon,
      iconPosition = 'left',
      suffix,
      size = 'md',
      fullWidth = true,
      className,
      containerClassName,
      labelClassName,
      type = 'text',
      ...props
    },
    ref
  ) => {
    const [showPassword, setShowPassword] = useState(false)
    const isPassword = type === 'password'
    const actualType = isPassword && showPassword ? 'text' : type
    const sz = sizeMap[size]

    const hasLeftIcon = icon && iconPosition === 'left'
    const hasRightIcon = (icon && iconPosition === 'right') || isPassword || error

    return (
      <div className={cn('flex flex-col gap-1.5', fullWidth && 'w-full', containerClassName)}>
        {/* Label */}
        {label && (
          <label
            className={cn(
              sz.label,
              'font-medium text-white/70 tracking-wide',
              error && 'text-red-400',
              labelClassName
            )}
            htmlFor={props.id}
          >
            {label}
            {props.required && <span className="text-red-400 ml-1">*</span>}
          </label>
        )}

        {/* Input wrapper */}
        <div className="relative flex items-center">
          {/* Left icon */}
          {hasLeftIcon && (
            <span
              className={cn(
                'absolute left-3 flex items-center pointer-events-none z-10',
                error ? 'text-red-400' : 'text-white/35',
                sz.icon
              )}
            >
              {icon}
            </span>
          )}

          {/* Input field */}
          <input
            ref={ref}
            type={actualType}
            className={cn(
              'w-full rounded-xl',
              'backdrop-blur-[10px]',
              'border transition-all duration-200 outline-none',
              sz.input,
              hasLeftIcon ? sz.paddingLeftWithIcon : sz.paddingLeft,
              (hasRightIcon || suffix) ? sz.paddingRightWithIcon : sz.paddingRight,
              // States
              error
                ? [
                    'bg-red-500/[0.07] border-red-500/40 text-red-200',
                    'focus:bg-red-500/[0.1] focus:border-red-400',
                    'focus:ring-2 focus:ring-red-500/20',
                  ]
                : [
                    'bg-white/[0.06] border-white/[0.12] text-white',
                    'placeholder:text-white/30',
                    'hover:bg-white/[0.08] hover:border-white/[0.18]',
                    'focus:bg-white/[0.09] focus:border-indigo-500/70',
                    'focus:ring-2 focus:ring-indigo-500/20',
                    'focus:shadow-[0_0_0_3px_rgba(99,102,241,0.12),0_4px_16px_rgba(0,0,0,0.2)]',
                  ],
              'disabled:opacity-40 disabled:cursor-not-allowed',
              'autofill:bg-transparent',
              className
            )}
            {...props}
          />

          {/* Right section */}
          <div className="absolute right-3 flex items-center gap-1.5 z-10">
            {/* Suffix text */}
            {suffix && !isPassword && (
              <span className="text-sm text-white/40 pointer-events-none">{suffix}</span>
            )}

            {/* Error icon */}
            {error && !isPassword && (
              <ExclamationCircleIcon className="w-4 h-4 text-red-400 shrink-0" />
            )}

            {/* Right position user icon */}
            {icon && iconPosition === 'right' && !isPassword && (
              <span className={cn('flex items-center text-white/35', sz.icon)}>{icon}</span>
            )}

            {/* Password toggle */}
            {isPassword && (
              <button
                type="button"
                tabIndex={-1}
                onClick={() => setShowPassword((v) => !v)}
                className="text-white/35 hover:text-white/70 transition-colors duration-150 p-0.5"
                aria-label={showPassword ? 'Hide password' : 'Show password'}
              >
                {showPassword ? (
                  <EyeSlashIcon className="w-4 h-4" />
                ) : (
                  <EyeIcon className="w-4 h-4" />
                )}
              </button>
            )}
          </div>
        </div>

        {/* Error / hint message */}
        <AnimatePresence mode="wait">
          {error ? (
            <motion.p
              key="error"
              initial={{ opacity: 0, y: -4, height: 0 }}
              animate={{ opacity: 1, y: 0, height: 'auto' }}
              exit={{ opacity: 0, y: -4, height: 0 }}
              transition={{ duration: 0.2 }}
              className="text-xs text-red-400 flex items-center gap-1"
            >
              <ExclamationCircleIcon className="w-3.5 h-3.5 shrink-0" />
              {error}
            </motion.p>
          ) : hint ? (
            <motion.p
              key="hint"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              className="text-xs text-white/40"
            >
              {hint}
            </motion.p>
          ) : null}
        </AnimatePresence>
      </div>
    )
  }
)

GlassInput.displayName = 'GlassInput'

/* ── Textarea variant ───────────────────────────────────────────────────────── */
interface GlassTextareaProps extends React.TextareaHTMLAttributes<HTMLTextAreaElement> {
  label?: string
  error?: string
  hint?: string
  fullWidth?: boolean
  containerClassName?: string
  rows?: number
}

export const GlassTextarea = forwardRef<HTMLTextAreaElement, GlassTextareaProps>(
  ({ label, error, hint, fullWidth = true, className, containerClassName, rows = 4, ...props }, ref) => (
    <div className={cn('flex flex-col gap-1.5', fullWidth && 'w-full', containerClassName)}>
      {label && (
        <label
          className={cn('text-sm font-medium tracking-wide', error ? 'text-red-400' : 'text-white/70')}
          htmlFor={props.id}
        >
          {label}
          {props.required && <span className="text-red-400 ml-1">*</span>}
        </label>
      )}
      <textarea
        ref={ref}
        rows={rows}
        className={cn(
          'w-full rounded-xl px-4 py-3 text-sm',
          'backdrop-blur-[10px] resize-y min-h-[80px]',
          'border transition-all duration-200 outline-none',
          error
            ? 'bg-red-500/[0.07] border-red-500/40 text-red-200 focus:border-red-400 focus:ring-2 focus:ring-red-500/20'
            : [
                'bg-white/[0.06] border-white/[0.12] text-white',
                'placeholder:text-white/30',
                'hover:bg-white/[0.08] hover:border-white/[0.18]',
                'focus:bg-white/[0.09] focus:border-indigo-500/70',
                'focus:ring-2 focus:ring-indigo-500/20',
              ],
          className
        )}
        {...props}
      />
      {error && <p className="text-xs text-red-400">{error}</p>}
      {!error && hint && <p className="text-xs text-white/40">{hint}</p>}
    </div>
  )
)

GlassTextarea.displayName = 'GlassTextarea'

/* ── Select variant ─────────────────────────────────────────────────────────── */
interface GlassSelectProps extends React.SelectHTMLAttributes<HTMLSelectElement> {
  label?: string
  error?: string
  hint?: string
  fullWidth?: boolean
  containerClassName?: string
  options: { value: string; label: string }[]
  placeholder?: string
}

export const GlassSelect = forwardRef<HTMLSelectElement, GlassSelectProps>(
  ({ label, error, hint, fullWidth = true, className, containerClassName, options, placeholder, ...props }, ref) => (
    <div className={cn('flex flex-col gap-1.5', fullWidth && 'w-full', containerClassName)}>
      {label && (
        <label
          className={cn('text-sm font-medium tracking-wide', error ? 'text-red-400' : 'text-white/70')}
          htmlFor={props.id}
        >
          {label}
        </label>
      )}
      <select
        ref={ref}
        className={cn(
          'w-full rounded-xl px-4 py-2.5 text-sm',
          'backdrop-blur-[10px] appearance-none',
          'border transition-all duration-200 outline-none',
          'bg-white/[0.06] border-white/[0.12] text-white',
          'hover:bg-white/[0.08] hover:border-white/[0.18]',
          'focus:bg-white/[0.09] focus:border-indigo-500/70',
          'focus:ring-2 focus:ring-indigo-500/20',
          error && 'border-red-500/40',
          className
        )}
        {...props}
      >
        {placeholder && (
          <option value="" disabled className="bg-gray-900">
            {placeholder}
          </option>
        )}
        {options.map((opt) => (
          <option key={opt.value} value={opt.value} className="bg-gray-900">
            {opt.label}
          </option>
        ))}
      </select>
      {error && <p className="text-xs text-red-400">{error}</p>}
      {!error && hint && <p className="text-xs text-white/40">{hint}</p>}
    </div>
  )
)

GlassSelect.displayName = 'GlassSelect'

export default GlassInput
