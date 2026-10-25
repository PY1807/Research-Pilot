import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { sourceFileUrl, type SearchResult } from '../api'
import { SearchResults } from './SearchResults'

const result: SearchResult = {
  chunk_id: 'c1',
  source_id: 's1',
  source_title: 'Lost in the Middle',
  page_number: 4,
  text: 'Performance is highest when relevant information is at the start or end.',
  score: 0.8791,
}

describe('SearchResults', () => {
  it('shows the passage, its source, and a link to the exact page', () => {
    render(<SearchResults results={[result]} />)

    expect(screen.getByText('Lost in the Middle')).toBeInTheDocument()
    expect(screen.getByText(/relevant information is at the start/)).toBeInTheDocument()
    expect(screen.getByText('score 0.879')).toBeInTheDocument()
    const link = screen.getByRole('link', { name: /p\. 4/ })
    expect(link).toHaveAttribute('href', '/api/sources/s1/file/#page=4')
    expect(link).toHaveAttribute('target', '_blank')
  })

  it('explains an empty result list', () => {
    render(<SearchResults results={[]} />)

    expect(screen.getByText(/No passages found/)).toBeInTheDocument()
  })
})

describe('sourceFileUrl', () => {
  it('adds a page anchor only when a page is known', () => {
    expect(sourceFileUrl('abc', 7)).toBe('/api/sources/abc/file/#page=7')
    expect(sourceFileUrl('abc')).toBe('/api/sources/abc/file/')
    expect(sourceFileUrl('abc', null)).toBe('/api/sources/abc/file/')
  })
})
