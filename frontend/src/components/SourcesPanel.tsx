import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useRef, useState, type DragEvent } from 'react'

import { api, sourceFileUrl, type Source } from '../api'
import { StatusPill } from './StatusPill'

type UploadNote = { name: string; error: string }

const isBusy = (s: Source) => s.status === 'pending' || s.status === 'processing'

export function SourcesPanel({ projectId }: { projectId: string }) {
  const queryClient = useQueryClient()
  const inputRef = useRef<HTMLInputElement>(null)
  const [dragging, setDragging] = useState(false)
  const [notes, setNotes] = useState<UploadNote[]>([])

  const sources = useQuery({
    queryKey: ['sources', projectId],
    queryFn: () => api.listSources(projectId),
    // Poll every 2 s while anything is still being ingested, then stop.
    refetchInterval: (query) => (query.state.data?.some(isBusy) ? 2000 : false),
  })

  const upload = useMutation({
    mutationFn: async (files: File[]) => {
      const failures: UploadNote[] = []
      for (const file of files) {
        try {
          await api.uploadSource(projectId, file)
        } catch (err) {
          failures.push({ name: file.name, error: err instanceof Error ? err.message : 'Upload failed' })
        }
        await queryClient.invalidateQueries({ queryKey: ['sources', projectId] })
      }
      return failures
    },
    onSuccess: setNotes,
  })

  function handleFiles(fileList: FileList | null) {
    const files = Array.from(fileList ?? [])
    if (files.length > 0) upload.mutate(files)
  }

  function onDrop(event: DragEvent) {
    event.preventDefault()
    setDragging(false)
    handleFiles(event.dataTransfer.files)
  }

  const list = sources.data ?? []
  const ready = list.filter((s) => s.status === 'ready').length

  return (
    <section className="grid gap-4">
      <div className="flex items-baseline justify-between">
        <h2 className="font-serif text-lg font-semibold">Sources</h2>
        <span className="font-mono text-xs text-muted">
          {ready}/{list.length} ready
        </span>
      </div>

      <button
        type="button"
        onClick={() => inputRef.current?.click()}
        onDragOver={(e) => {
          e.preventDefault()
          setDragging(true)
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
        className={`rounded-lg border border-dashed p-5 text-center text-sm transition-colors ${
          dragging ? 'border-accent bg-accent-soft' : 'border-line bg-surface hover:border-accent'
        }`}
      >
        {upload.isPending ? (
          'Uploading…'
        ) : (
          <>
            <span className="font-medium text-accent">Upload PDFs</span>
            <span className="text-muted"> or drop them here · up to 50 MB each</span>
          </>
        )}
      </button>
      <input
        id="pdf-upload"
        ref={inputRef}
        type="file"
        accept="application/pdf"
        multiple
        hidden
        onChange={(e) => {
          handleFiles(e.target.files)
          e.target.value = ''
        }}
      />

      {notes.length > 0 && (
        <ul className="grid gap-1 rounded-md border border-bad/40 p-3 text-sm text-bad" role="alert">
          {notes.map((n) => (
            <li key={n.name}>
              <span className="font-medium">{n.name}:</span> {n.error}
            </li>
          ))}
        </ul>
      )}

      {sources.isError && <p className="text-sm text-bad">Couldn't load sources: {sources.error.message}</p>}

      <ul className="grid divide-y divide-line rounded-lg border border-line bg-surface">
        {list.length === 0 && !sources.isLoading && (
          <li className="p-4 text-sm text-muted">No sources yet. Upload a PDF to start.</li>
        )}
        {list.map((source) => (
          <li key={source.id} className="grid gap-1 px-4 py-3">
            <div className="flex items-start justify-between gap-3">
              <a
                href={sourceFileUrl(source.id)}
                target="_blank"
                rel="noreferrer"
                className="min-w-0 break-words text-sm font-medium hover:text-accent"
              >
                {source.title}
              </a>
              <StatusPill status={source.status} />
            </div>
            {source.status === 'ready' && (
              <p className="font-mono text-xs text-muted">
                {source.metadata.page_count} pages · {source.metadata.chunk_count} chunks
              </p>
            )}
            {source.status === 'failed' && source.error && (
              <p className="text-xs text-bad">{source.error}</p>
            )}
          </li>
        ))}
      </ul>
    </section>
  )
}
