import { sourceFileUrl, type Answer, type AnswerPassage } from '../api'

/** Citation chip: "S3" becomes a numbered link to the exact PDF page. */
function CitationLink({ passage }: { passage: AnswerPassage }) {
  return (
    <a
      href={sourceFileUrl(passage.source_id, passage.page_number)}
      target="_blank"
      rel="noreferrer"
      title={`${passage.source_title}, p. ${passage.page_number ?? '?'}`}
      className="ml-1 rounded bg-mark px-1 font-mono text-xs text-mark-ink hover:underline"
    >
      {passage.label.slice(1)}
    </a>
  )
}

function UsageLine({ answer }: { answer: Answer }) {
  const u = answer.usage
  if (!u) return null
  const tokens = (u.input_tokens + u.output_tokens).toLocaleString()
  const seconds = ((u.latency_ms + answer.retrieval_ms) / 1000).toFixed(1)
  return (
    <p className="font-mono text-xs text-muted">
      {u.provider} · {u.model} · {tokens} tokens · {seconds}s
      {u.cost_usd > 0 && ` · $${u.cost_usd.toFixed(4)}`}
    </p>
  )
}

export function AnswerView({ answer }: { answer: Answer }) {
  const byLabel = new Map(answer.passages.map((p) => [p.label, p]))
  const cited = answer.passages.filter((p) => p.cited)

  return (
    <div className="grid gap-4 rounded-lg border border-line bg-surface p-4">
      {!answer.answerable && (
        <p className="rounded-md border border-warn/40 bg-warn/10 px-3 py-2 text-sm">
          <strong>Not enough evidence.</strong>{' '}
          {answer.missing_information ?? 'The sources don’t answer this question.'}
        </p>
      )}

      {answer.claims.length > 0 && (
        <div className="grid gap-2 text-sm leading-relaxed">
          {answer.claims.map((claim, i) => (
            <p key={i}>
              {claim.text}
              {claim.citations.map((label) => {
                const passage = byLabel.get(label)
                return passage ? <CitationLink key={label} passage={passage} /> : null
              })}
              {claim.citations.length === 0 && (
                <span
                  className="ml-1 rounded border border-bad/40 px-1 text-xs text-bad"
                  title="The model made this claim without citing a passage. Treat it as unverified."
                >
                  no citation
                </span>
              )}
            </p>
          ))}
        </div>
      )}

      {answer.answerable && answer.missing_information && (
        <p className="text-sm text-muted">
          <strong>Gap:</strong> {answer.missing_information}
        </p>
      )}

      {answer.dropped_citations.length > 0 && (
        <p className="text-xs text-warn">
          {answer.dropped_citations.length} citation(s) pointed at passages the model was never
          shown and were removed.
        </p>
      )}

      {cited.length > 0 && (
        <div className="grid gap-2 border-t border-line pt-3">
          <h3 className="text-xs font-semibold uppercase tracking-wide text-muted">Sources</h3>
          <ol className="grid gap-2">
            {cited.map((p) => (
              <li key={p.label} className="text-sm">
                <details>
                  <summary className="cursor-pointer">
                    <span className="mr-2 font-mono text-muted">{p.label.slice(1)}.</span>
                    <span>{p.source_title}</span>{' '}
                    <a
                      href={sourceFileUrl(p.source_id, p.page_number)}
                      target="_blank"
                      rel="noreferrer"
                      className="font-mono text-xs text-accent hover:underline"
                    >
                      p. {p.page_number ?? '?'} ↗
                    </a>
                  </summary>
                  <p className="mt-1 border-l-2 border-line pl-3 text-ink/80">{p.text}</p>
                </details>
              </li>
            ))}
          </ol>
        </div>
      )}

      <UsageLine answer={answer} />
    </div>
  )
}
