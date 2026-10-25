import { useQuery } from '@tanstack/react-query'
import { Link, useParams } from 'react-router-dom'

import { api } from '../api'
import { SearchPanel } from '../components/SearchPanel'
import { SourcesPanel } from '../components/SourcesPanel'

export default function ProjectPage() {
  const { projectId = '' } = useParams()
  const project = useQuery({ queryKey: ['project', projectId], queryFn: () => api.getProject(projectId) })

  if (project.isLoading) return <p className="text-muted">Loading project…</p>
  if (project.isError) {
    return (
      <p className="text-bad">
        {project.error.message}{' '}
        <Link to="/" className="underline">
          Back to projects
        </Link>
      </p>
    )
  }

  return (
    <div className="grid gap-8">
      <div className="grid gap-2">
        <Link to="/" className="text-sm text-muted hover:text-accent">
          ← Projects
        </Link>
        <h1 className="font-serif text-3xl font-semibold">{project.data?.title}</h1>
        <p className="max-w-3xl text-muted">{project.data?.question}</p>
      </div>

      <div className="grid gap-8 lg:grid-cols-[minmax(0,2fr)_minmax(0,3fr)]">
        <SourcesPanel projectId={projectId} />
        <SearchPanel projectId={projectId} />
      </div>
    </div>
  )
}
