import { useMutation } from '@tanstack/react-query'
import { useState, type FormEvent } from 'react'

import { api } from '../api'
import { AnswerView } from './AnswerView'

export function AskPanel({ projectId }: { projectId: string }) {
  const [question, setQuestion] = useState('')
  const ask = useMutation({ mutationFn: (q: string) => api.answer(projectId, q) })

  function onSubmit(event: FormEvent) {
    event.preventDefault()
    if (question.trim()) ask.mutate(question.trim())
  }

  return (
    <section className="grid gap-4">
      <h2 className="font-serif text-lg font-semibold">Ask for a cited answer</h2>
      <form onSubmit={onSubmit} className="flex gap-2">
        <label htmlFor="ask-question" className="sr-only">
          Question
        </label>
        <input
          id="ask-question"
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          placeholder="e.g. When does long-context prompting beat RAG?"
          className="min-w-0 flex-1 rounded-md border border-line bg-surface px-3 py-2 text-sm placeholder:text-muted focus:border-accent focus:outline-none"
        />
        <button
          type="submit"
          disabled={!question.trim() || ask.isPending}
          className="rounded-md bg-accent px-4 py-2 text-sm font-medium text-white disabled:opacity-50 dark:text-paper"
        >
          {ask.isPending ? 'Answering…' : 'Ask'}
        </button>
      </form>

      {ask.isError && <p className="text-sm text-bad">{ask.error.message}</p>}
      {ask.data && <AnswerView answer={ask.data} />}
      {!ask.data && !ask.isPending && (
        <p className="text-sm text-muted">
          The answer uses only your sources. Every sentence links to the page it came from, and
          it says so when the evidence isn’t there.
        </p>
      )}
    </section>
  )
}
