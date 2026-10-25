import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { StatusPill } from './StatusPill'

describe('StatusPill', () => {
  it.each([
    ['pending', 'Queued'],
    ['processing', 'Processing'],
    ['ready', 'Ready'],
    ['failed', 'Failed'],
  ] as const)('labels %s as %s', (status, label) => {
    render(<StatusPill status={status} />)

    expect(screen.getByText(label)).toBeInTheDocument()
  })
})
