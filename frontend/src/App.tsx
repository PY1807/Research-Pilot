import { useEffect, useState } from 'react'

type Health = { status: string; database: string }

type HealthState =
  | { kind: 'loading' }
  | { kind: 'ok'; health: Health }
  | { kind: 'error'; message: string }

function App() {
  const [state, setState] = useState<HealthState>({ kind: 'loading' })

  useEffect(() => {
    fetch('/api/health')
      .then(async (res) => {
        const body = (await res.json()) as Health
        setState(res.ok ? { kind: 'ok', health: body } : { kind: 'error', message: `API returned ${res.status}` })
      })
      .catch(() => setState({ kind: 'error', message: 'Could not reach the API. Is it running?' }))
  }, [])

  return (
    <main className="shell">
      <h1>ResearchPilot</h1>
      <p className="tagline">Evidence-first research workspace</p>

      <section className="status" aria-live="polite">
        {state.kind === 'loading' && <p>Checking API…</p>}
        {state.kind === 'ok' && (
          <p>
            API: <strong>{state.health.status}</strong> · Database: <strong>{state.health.database}</strong>
          </p>
        )}
        {state.kind === 'error' && <p className="error">{state.message}</p>}
      </section>
    </main>
  )
}

export default App
