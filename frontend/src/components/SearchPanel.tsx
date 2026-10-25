import { useQuery } from '@tanstack/react-query'
import { useState, type FormEvent } from 'react'

import { api } from '../api'
import { SearchResults } from './SearchResults'

export function SearchPanel({ projectId }: { projectId: string }) {
  const [draft, setDraft] = useState('')
  const [query, setQuery] = useState('')

  const results = useQuery({
    queryKey: ['search', projectId, query],
    queryFn: () => api.search(projectId, query, 5),
    enabled: query.length > 0,
  })

  function onSubmit(event: FormEvent) {
    event.preventDefault()
    setQuery(draft.trim())
  }

  return (
    <section className="grid gap-4">
      <h2 className="font-serif text-lg font-semibold">Search the evidence</h2>
      <form onSubmit={onSubmit} className="flex gap-2">
        <label htmlFor="search-query" className="sr-only">
          Question
        </label>
        <input
          id="search-query"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          placeholder="Ask a question, e.g. When does long context beat retrieval?"
          className="min-w-0 flex-1 rounded-md border border-line bg-surface px-3 py-2 text-sm placeholder:text-muted focus:border-accent focus:outline-none"
        />
        <button
          type="submit"
          disabled={!draft.trim() || results.isFetching}
          className="rounded-md bg-accent px-4 py-2 text-sm font-medium text-white disabled:opacity-50 dark:text-paper"
        >
          {results.isFetching ? 'Searching…' : 'Search'}
        </button>
      </form>

      {results.isError && <p className="text-sm text-bad">Search failed: {results.error.message}</p>}
      {results.data && <SearchResults results={results.data} />}
      {!query && (
        <p className="text-sm text-muted">
          Results are passages ranked by meaning, not just matching words. Each one links to the
          exact page it came from.
        </p>
      )}
    </section>
  )
}
