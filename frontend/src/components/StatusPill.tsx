import type { IngestionStatus } from '../api'

const STYLES: Record<IngestionStatus, { label: string; className: string }> = {
  pending: { label: 'Queued', className: 'text-muted border-line' },
  processing: { label: 'Processing', className: 'text-warn border-warn/40' },
  ready: { label: 'Ready', className: 'text-ok border-ok/40' },
  failed: { label: 'Failed', className: 'text-bad border-bad/40' },
}

export function StatusPill({ status }: { status: IngestionStatus }) {
  const { label, className } = STYLES[status]
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 font-mono text-xs ${className}`}
    >
      {(status === 'pending' || status === 'processing') && (
        <span className="size-1.5 animate-pulse rounded-full bg-current" aria-hidden />
      )}
      {label}
    </span>
  )
}
