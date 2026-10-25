import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'

import { api } from '../api'

export default function ProjectsPage() {
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const [title, setTitle] = useState('')
  const [question, setQuestion] = useState('')

  const projects = useQuery({ queryKey: ['projects'], queryFn: api.listProjects })

  const create = useMutation({
    mutationFn: api.createProject,
    onSuccess: async (project) => {
      await queryClient.invalidateQueries({ queryKey: ['projects'] })
      navigate(`/projects/${project.id}`)
    },
  })

  function onSubmit(event: FormEvent) {
    event.preventDefault()
    create.mutate({ title: title.trim(), question: question.trim() })
  }

  return (
    <div className="grid gap-10 lg:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
      <section className="grid content-start gap-4">
        <h1 className="font-serif text-3xl font-semibold">Projects</h1>
        {projects.isLoading && <p className="text-muted">Loading…</p>}
        {projects.isError && <p className="text-bad">Couldn't load projects: {projects.error.message}</p>}
        {projects.data?.length === 0 && (
          <p className="text-muted">No projects yet. Create one to start collecting evidence.</p>
        )}
        <ul className="grid gap-3">
          {projects.data?.map((project) => (
            <li key={project.id}>
              <Link
                to={`/projects/${project.id}`}
                className="block rounded-lg border border-line bg-surface p-4 hover:border-accent"
              >
                <p className="font-medium">{project.title}</p>
                <p className="mt-1 line-clamp-2 text-sm text-muted">{project.question}</p>
              </Link>
            </li>
          ))}
        </ul>
      </section>

      <section className="grid content-start gap-4">
        <h2 className="font-serif text-lg font-semibold">New project</h2>
        <form onSubmit={onSubmit} className="grid gap-3 rounded-lg border border-line bg-surface p-4">
          <label className="grid gap-1 text-sm">
            <span className="font-medium">Title</span>
            <input
              id="project-title"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="RAG vs long-context LLMs"
              className="rounded-md border border-line bg-paper px-3 py-2 focus:border-accent focus:outline-none"
            />
          </label>
          <label className="grid gap-1 text-sm">
            <span className="font-medium">Research question</span>
            <textarea
              id="project-question"
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              rows={3}
              placeholder="When is retrieval better than putting everything in the prompt?"
              className="rounded-md border border-line bg-paper px-3 py-2 focus:border-accent focus:outline-none"
            />
          </label>
          {create.isError && <p className="text-sm text-bad">{create.error.message}</p>}
          <button
            type="submit"
            disabled={!title.trim() || !question.trim() || create.isPending}
            className="rounded-md bg-accent px-4 py-2 text-sm font-medium text-white disabled:opacity-50 dark:text-paper"
          >
            {create.isPending ? 'Creating…' : 'Create project'}
          </button>
        </form>
      </section>
    </div>
  )
}
