import { useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { SparklesIcon, PaperAirplaneIcon, ClockIcon } from '@heroicons/react/24/outline'
import { GlassCard } from '../../components/ui/GlassCard'
import { aiApi } from '../../services/api'

const SUGGESTIONS = [
  'How much did I spend on HVAC this year?',
  'Which property has the highest vacancy rate?',
  'Show me overdue invoices this quarter',
  'What maintenance is coming up next month?',
  'List top 3 vendors by total spend',
  'Compare income vs expenses for last 6 months',
]

interface Message { role: 'user' | 'ai'; content: string; data?: any }

export default function AISearch() {
  const [query, setQuery] = useState('')
  const [messages, setMessages] = useState<Message[]>([])
  const [loading, setLoading] = useState(false)

  const handleSubmit = async (q?: string) => {
    const text = (q ?? query).trim()
    if (!text) return
    setMessages(m => [...m, { role: 'user', content: text }])
    setQuery('')
    setLoading(true)
    try {
      const res = await aiApi.query(text)
      setMessages(m => [...m, { role: 'ai', content: res.data.answer ?? JSON.stringify(res.data), data: res.data }])
    } catch (err: any) {
      setMessages(m => [...m, { role: 'ai', content: 'Sorry, I could not process that query. Please try again.' }])
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="max-w-3xl mx-auto space-y-6">
      {/* Hero */}
      <div className="text-center py-6">
        <div className="w-16 h-16 rounded-2xl bg-gradient-to-br from-indigo-500 to-purple-600 flex items-center justify-center mx-auto mb-4 shadow-lg shadow-indigo-500/30">
          <SparklesIcon className="w-8 h-8 text-white" />
        </div>
        <h2 className="text-2xl font-bold text-white">AI Property Intelligence</h2>
        <p className="text-white/50 mt-2 text-sm">Ask anything about your portfolio in plain English</p>
      </div>

      {/* Messages */}
      <AnimatePresence>
        {messages.length > 0 && (
          <div className="space-y-4">
            {messages.map((msg, i) => (
              <motion.div
                key={i}
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
              >
                {msg.role === 'ai' && (
                  <div className="w-7 h-7 rounded-full bg-gradient-to-br from-indigo-500 to-purple-600 flex items-center justify-center mr-3 flex-shrink-0 mt-1">
                    <SparklesIcon className="w-4 h-4 text-white" />
                  </div>
                )}
                <div className={`max-w-[85%] px-4 py-3 rounded-2xl text-sm ${
                  msg.role === 'user'
                    ? 'bg-indigo-600/40 border border-indigo-500/30 text-white rounded-br-sm'
                    : 'glass-card border border-white/10 text-white/90 rounded-bl-sm'
                }`}>
                  {msg.content}
                </div>
              </motion.div>
            ))}
            {loading && (
              <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="flex items-center gap-3">
                <div className="w-7 h-7 rounded-full bg-gradient-to-br from-indigo-500 to-purple-600 flex items-center justify-center">
                  <SparklesIcon className="w-4 h-4 text-white" />
                </div>
                <div className="glass-card px-4 py-3 rounded-2xl rounded-bl-sm border border-white/10">
                  <div className="flex gap-1">
                    {[0, 1, 2].map(i => (
                      <motion.div key={i} animate={{ opacity: [0.3, 1, 0.3] }} transition={{ duration: 1.2, repeat: Infinity, delay: i * 0.2 }} className="w-2 h-2 bg-indigo-400 rounded-full" />
                    ))}
                  </div>
                </div>
              </motion.div>
            )}
          </div>
        )}
      </AnimatePresence>

      {/* Suggestions */}
      {messages.length === 0 && (
        <GlassCard>
          <p className="text-sm font-medium text-white/50 mb-3 flex items-center gap-2">
            <ClockIcon className="w-4 h-4" /> Try asking…
          </p>
          <div className="grid sm:grid-cols-2 gap-2">
            {SUGGESTIONS.map(s => (
              <button
                key={s}
                onClick={() => handleSubmit(s)}
                className="text-left text-sm text-white/70 hover:text-white px-3 py-2.5 rounded-xl bg-white/5 hover:bg-white/10 border border-white/8 hover:border-white/15 transition-all"
              >
                {s}
              </button>
            ))}
          </div>
        </GlassCard>
      )}

      {/* Input */}
      <GlassCard className="sticky bottom-4">
        <form onSubmit={e => { e.preventDefault(); handleSubmit() }} className="flex gap-3">
          <input
            value={query}
            onChange={e => setQuery(e.target.value)}
            placeholder="Ask anything about your portfolio…"
            disabled={loading}
            className="flex-1 bg-transparent text-white placeholder-white/30 text-sm focus:outline-none"
          />
          <button
            type="submit"
            disabled={!query.trim() || loading}
            className="p-2 rounded-xl bg-indigo-600 hover:bg-indigo-500 disabled:opacity-40 disabled:cursor-not-allowed text-white transition-colors"
          >
            <PaperAirplaneIcon className="w-5 h-5" />
          </button>
        </form>
      </GlassCard>
    </div>
  )
}
