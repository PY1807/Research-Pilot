import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import type { Answer } from '../api'
import { AnswerView } from './AnswerView'

const passage = {
  chunk_id: 'c1',
  source_id: 'src1',
  source_title: 'Lost in the Middle',
  page_number: 4,
  text: 'Performance is highest when relevant information is at the start or end.',
  score: 0.03,
}

const answer: Answer = {
  run_id: 'r1',
  question: 'Where should key facts go?',
  answerable: true,
  claims: [
    { text: 'Models use facts at the start or end best.', citations: ['S1'] },
    { text: 'An unsupported aside.', citations: [] },
  ],
  passages: [
    { ...passage, label: 'S1', cited: true },
    { ...passage, label: 'S2', cited: false, chunk_id: 'c2', source_title: 'Unused paper' },
  ],
  missing_information: null,
  dropped_citations: ['S9'],
  retrieval_mode: 'hybrid',
  retrieval_ms: 50,
  usage: {
    provider: 'gemini',
    model: 'gemini-2.5-flash',
    calls: 1,
    input_tokens: 900,
    output_tokens: 100,
    cost_usd: 0,
    latency_ms: 1450,
  },
}

describe('AnswerView', () => {
  it('links each claim to the exact page of its cited passage', () => {
    render(<AnswerView answer={answer} />)

    expect(screen.getByText(/Models use facts at the start/)).toBeInTheDocument()
    const chip = screen.getByRole('link', { name: '1' })
    expect(chip).toHaveAttribute('href', '/api/sources/src1/file/#page=4')
    expect(chip).toHaveAttribute('title', 'Lost in the Middle, p. 4')
  })

  it('lists only cited sources, flags uncited claims and dropped citations', () => {
    render(<AnswerView answer={answer} />)

    expect(screen.getByText('Lost in the Middle')).toBeInTheDocument()
    expect(screen.queryByText('Unused paper')).not.toBeInTheDocument()
    expect(screen.getByText('no citation')).toBeInTheDocument()
    expect(screen.getByText(/1 citation\(s\) pointed at passages/)).toBeInTheDocument()
  })

  it('shows provider, tokens and time', () => {
    render(<AnswerView answer={answer} />)

    expect(screen.getByText('gemini · gemini-2.5-flash · 1,000 tokens · 1.5s')).toBeInTheDocument()
  })

  it('says plainly when the evidence is missing', () => {
    render(
      <AnswerView
        answer={{
          ...answer,
          answerable: false,
          claims: [],
          passages: [],
          dropped_citations: [],
          missing_information: 'No passage discusses pricing.',
        }}
      />,
    )

    expect(screen.getByText('Not enough evidence.')).toBeInTheDocument()
    expect(screen.getByText(/No passage discusses pricing/)).toBeInTheDocument()
  })
})
