import { useRef, useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { motion } from 'framer-motion'
import {
  DocumentIcon, ArrowUpTrayIcon, MagnifyingGlassIcon,
  ArrowDownTrayIcon, TrashIcon, SparklesIcon, FolderIcon,
} from '@heroicons/react/24/outline'
import { GlassCard } from '../../components/ui/GlassCard'
import { GlassButton } from '../../components/ui/GlassButton'
import { GlassBadge } from '../../components/ui/GlassBadge'
import { documentsApi } from '../../services/api'

interface Doc {
  id: string
  name: string
  category: string
  file_size?: number
  content_type?: string
  ai_summary?: string
  ai_category?: string
  tags?: string[]
  created_at: string
  property_id?: string
}

const CATEGORIES = ['lease', 'invoice', 'permit', 'insurance', 'maintenance', 'legal', 'financial', 'other']

function fileSize(bytes?: number) {
  if (!bytes) return ''
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}

function categoryColor(cat: string) {
  const map: Record<string, string> = {
    lease: 'text-indigo-400 bg-indigo-500/15 border-indigo-500/20',
    invoice: 'text-emerald-400 bg-emerald-500/15 border-emerald-500/20',
    permit: 'text-amber-400 bg-amber-500/15 border-amber-500/20',
    insurance: 'text-blue-400 bg-blue-500/15 border-blue-500/20',
    maintenance: 'text-orange-400 bg-orange-500/15 border-orange-500/20',
    legal: 'text-red-400 bg-red-500/15 border-red-500/20',
    financial: 'text-purple-400 bg-purple-500/15 border-purple-500/20',
  }
  return map[cat] ?? 'text-white/40 bg-white/8 border-white/10'
}

export default function DocumentsPage() {
  const [search, setSearch] = useState('')
  const [catFilter, setCatFilter] = useState('')
  const [uploading, setUploading] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const qc = useQueryClient()

  const { data, isLoading } = useQuery({
    queryKey: ['documents', search, catFilter],
    queryFn: () => documentsApi.list({ search: search || undefined, category: catFilter || undefined, limit: 50 }).then(r => r.data),
  })

  const deleteMutation = useMutation({
    mutationFn: (id: string) => documentsApi.delete(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['documents'] }),
  })

  const reprocessMutation = useMutation({
    mutationFn: (id: string) => documentsApi.reprocess(id),
  })

  const downloadMutation = useMutation({
    mutationFn: (id: string) => documentsApi.getSignedUrl(id).then(r => r.data),
    onSuccess: (data) => window.open(data.signed_url, '_blank'),
  })

  async function handleFileUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const files = e.target.files
    if (!files?.length) return
    setUploading(true)
    try {
      for (const file of Array.from(files)) {
        const fd = new FormData()
        fd.append('file', file)
        fd.append('category', 'other')
        await documentsApi.upload(fd)
      }
      qc.invalidateQueries({ queryKey: ['documents'] })
    } finally {
      setUploading(false)
      if (fileInputRef.current) fileInputRef.current.value = ''
    }
  }

  const docs: Doc[] = data?.documents ?? []

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-bold text-white">Documents</h2>
          <p className="text-white/40 text-sm mt-0.5">{data?.total ?? 0} files</p>
        </div>
        <div>
          <input ref={fileInputRef} type="file" multiple className="hidden" onChange={handleFileUpload} accept=".pdf,.doc,.docx,.jpg,.jpeg,.png" />
          <GlassButton
            variant="primary"
            icon={<ArrowUpTrayIcon className="w-4 h-4" />}
            onClick={() => fileInputRef.current?.click()}
            disabled={uploading}
          >
            {uploading ? 'Uploading…' : 'Upload'}
          </GlassButton>
        </div>
      </div>

      {/* Filters */}
      <GlassCard className="flex flex-wrap gap-3">
        <div className="relative flex-1 min-w-48">
          <MagnifyingGlassIcon className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-white/40" />
          <input
            value={search}
            onChange={e => setSearch(e.target.value)}
            placeholder="Search documents…"
            className="w-full bg-white/8 border border-white/15 rounded-xl pl-9 pr-4 py-2 text-sm text-white placeholder-white/30 focus:outline-none focus:border-indigo-500/60"
          />
        </div>
        <select
          value={catFilter}
          onChange={e => setCatFilter(e.target.value)}
          className="bg-white/8 border border-white/15 rounded-xl px-3 py-2 text-sm text-white focus:outline-none"
        >
          <option value="">All Categories</option>
          {CATEGORIES.map(c => <option key={c} value={c} className="capitalize">{c}</option>)}
        </select>
      </GlassCard>

      {/* Category quick-filter pills */}
      <div className="flex flex-wrap gap-2">
        {CATEGORIES.map(c => (
          <button
            key={c}
            onClick={() => setCatFilter(catFilter === c ? '' : c)}
            className={`px-3 py-1 rounded-full text-xs font-medium border transition-colors capitalize ${
              catFilter === c ? categoryColor(c) : 'bg-white/5 border-white/10 text-white/40 hover:border-white/20'
            }`}
          >
            {c}
          </button>
        ))}
      </div>

      {/* Drop zone hint when empty */}
      {!isLoading && docs.length === 0 && (
        <div
          className="border-2 border-dashed border-white/15 rounded-2xl p-12 text-center cursor-pointer hover:border-indigo-500/40 transition-colors"
          onClick={() => fileInputRef.current?.click()}
        >
          <FolderIcon className="w-12 h-12 mx-auto mb-3 text-white/20" />
          <p className="text-white/30 text-sm">No documents yet — click to upload</p>
        </div>
      )}

      {/* Document grid */}
      {isLoading ? (
        <div className="flex items-center justify-center h-48">
          <div className="w-8 h-8 border-2 border-indigo-500 border-t-transparent rounded-full animate-spin" />
        </div>
      ) : (
        <div className="grid sm:grid-cols-2 xl:grid-cols-3 gap-4">
          {docs.map((doc, i) => (
            <motion.div key={doc.id} initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.04 }}>
              <GlassCard>
                <div className="flex items-start gap-3 mb-3">
                  <div className="p-2 rounded-lg bg-white/5 border border-white/10 shrink-0">
                    <DocumentIcon className="w-5 h-5 text-white/50" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-white truncate">{doc.name}</p>
                    <div className="flex items-center gap-2 mt-1">
                      <span className={`text-xs px-2 py-0.5 rounded-full border capitalize ${categoryColor(doc.ai_category ?? doc.category)}`}>
                        {doc.ai_category ?? doc.category}
                      </span>
                      {doc.file_size && <span className="text-xs text-white/30">{fileSize(doc.file_size)}</span>}
                    </div>
                  </div>
                </div>

                {doc.ai_summary && (
                  <div className="mb-3 px-3 py-2 rounded-lg bg-indigo-500/10 border border-indigo-500/20">
                    <div className="flex items-center gap-1.5 mb-1">
                      <SparklesIcon className="w-3 h-3 text-indigo-400" />
                      <span className="text-xs text-indigo-400 font-medium">AI Summary</span>
                    </div>
                    <p className="text-xs text-white/60 line-clamp-2">{doc.ai_summary}</p>
                  </div>
                )}

                {doc.tags && doc.tags.length > 0 && (
                  <div className="flex flex-wrap gap-1 mb-3">
                    {doc.tags.slice(0, 3).map(t => (
                      <span key={t} className="text-xs px-2 py-0.5 rounded-full bg-white/5 border border-white/10 text-white/40">{t}</span>
                    ))}
                  </div>
                )}

                <div className="flex items-center justify-between">
                  <span className="text-xs text-white/30">{new Date(doc.created_at).toLocaleDateString()}</span>
                  <div className="flex items-center gap-1">
                    <button
                      onClick={() => reprocessMutation.mutate(doc.id)}
                      className="p-1.5 rounded-lg hover:bg-indigo-500/15 text-white/40 hover:text-indigo-400 transition-colors"
                      title="Re-classify with AI"
                    >
                      <SparklesIcon className="w-4 h-4" />
                    </button>
                    <button
                      onClick={() => downloadMutation.mutate(doc.id)}
                      className="p-1.5 rounded-lg hover:bg-white/10 text-white/40 hover:text-white transition-colors"
                      title="Download"
                    >
                      <ArrowDownTrayIcon className="w-4 h-4" />
                    </button>
                    <button
                      onClick={() => { if (confirm('Delete this document?')) deleteMutation.mutate(doc.id) }}
                      className="p-1.5 rounded-lg hover:bg-red-500/15 text-white/40 hover:text-red-400 transition-colors"
                      title="Delete"
                    >
                      <TrashIcon className="w-4 h-4" />
                    </button>
                  </div>
                </div>
              </GlassCard>
            </motion.div>
          ))}
        </div>
      )}
    </div>
  )
}
