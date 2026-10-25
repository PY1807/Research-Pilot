import { Link, Route, Routes } from 'react-router-dom'

import ProjectPage from './pages/ProjectPage'
import ProjectsPage from './pages/ProjectsPage'

function App() {
  return (
    <div className="min-h-screen">
      <header className="border-b border-line bg-surface">
        <div className="mx-auto flex max-w-6xl items-baseline gap-3 px-4 py-4 sm:px-6">
          <Link to="/" className="font-serif text-xl font-semibold tracking-tight">
            ResearchPilot
          </Link>
          <span className="hidden text-sm text-muted sm:inline">Evidence-first research workspace</span>
        </div>
      </header>

      <main className="mx-auto max-w-6xl px-4 py-8 sm:px-6">
        <Routes>
          <Route path="/" element={<ProjectsPage />} />
          <Route path="/projects/:projectId" element={<ProjectPage />} />
          <Route path="*" element={<p className="text-muted">Page not found.</p>} />
        </Routes>
      </main>
    </div>
  )
}

export default App
