import { sourceFileUrl, type SearchResult } from '../api'

function MatchedBy({ result }: { result: SearchResult }) {
  const parts = [
    result.semantic_rank && `meaning #${result.semantic_rank}`,
    result.keyword_rank && `keywords #${result.keyword_rank}`,
  ].filter(Boolean)
  return (
    <span className="text-muted" title="Where each search method ranked this passage">
      {parts.join(' · ')}
    </span>
  )
}

export function SearchResults({ results }: { results: SearchResult[] }) {
  if (results.length === 0) {
    return <p className="text-sm text-muted">No passages found. Are any sources ready yet?</p>
  }

  return (
    <ol className="grid gap-3">
      {results.map((result, i) => (
        <li key={result.chunk_id} className="rounded-lg border border-line bg-surface p-4">
          <div className="mb-2 flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
            <p className="min-w-0 text-sm font-medium">
              <span className="mr-2 font-mono text-muted">{i + 1}.</span>
              {result.source_title}
            </p>
            <div className="flex flex-wrap items-baseline gap-3 font-mono text-xs">
              <MatchedBy result={result} />
              <a
                href={sourceFileUrl(result.source_id, result.page_number)}
                target="_blank"
                rel="noreferrer"
                className="rounded bg-mark px-1.5 py-0.5 text-mark-ink hover:underline"
              >
                p. {result.page_number ?? '?'} ↗
              </a>
            </div>
          </div>
          <p className="text-sm leading-relaxed text-ink/90">{result.text}</p>
        </li>
      ))}
    </ol>
  )
}
