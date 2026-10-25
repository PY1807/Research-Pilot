// Typed client for the FastAPI backend. Every request goes through /api, which Vite
// proxies to the API server, so there is no CORS setup.

export type Project = {
  id: string
  title: string
  question: string
  scope: Record<string, unknown>
  created_at: string
}

export type IngestionStatus = 'pending' | 'processing' | 'ready' | 'failed'

export type Source = {
  id: string
  project_id: string
  title: string
  source_type: 'uploaded' | 'external'
  status: IngestionStatus
  error: string | null
  checksum: string | null
  metadata: { page_count?: number; chunk_count?: number; original_filename?: string }
  created_at: string
}

export type SearchMode = 'hybrid' | 'semantic' | 'keyword'

export type SearchResult = {
  chunk_id: string
  source_id: string
  source_title: string
  page_number: number | null
  text: string
  /** Mode-specific: cosine similarity, keyword rank score, or RRF score. */
  score: number
  semantic_rank: number | null
  keyword_rank: number | null
}

export class ApiError extends Error {
  status: number

  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`/api${path}`, init)
  if (!response.ok) {
    let message = `Request failed (${response.status})`
    try {
      const body = await response.json()
      if (typeof body.detail === 'string') message = body.detail
      else if (Array.isArray(body.detail)) {
        message = body.detail.map((d: { msg: string }) => d.msg).join('; ')
      }
    } catch {
      // Non-JSON error body; keep the generic message.
    }
    throw new ApiError(response.status, message)
  }
  return response.json() as Promise<T>
}

export const api = {
  listProjects: () => request<Project[]>('/projects/'),

  getProject: (id: string) => request<Project>(`/projects/${id}/`),

  createProject: (body: { title: string; question: string }) =>
    request<Project>('/projects/', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }),

  listSources: (projectId: string) => request<Source[]>(`/projects/${projectId}/sources/`),

  uploadSource: (projectId: string, file: File) => {
    const form = new FormData()
    form.append('file', file)
    return request<Source>(`/projects/${projectId}/sources/`, { method: 'POST', body: form })
  },

  search: (projectId: string, query: string, mode: SearchMode = 'hybrid', k = 5) =>
    request<SearchResult[]>(
      `/projects/${projectId}/search/?${new URLSearchParams({ q: query, k: String(k), mode })}`,
    ),
}

/** Link to the original PDF; browsers' built-in viewers jump to `#page=N`. */
export function sourceFileUrl(sourceId: string, page?: number | null): string {
  return `/api/sources/${sourceId}/file/${page ? `#page=${page}` : ''}`
}
