import { describe, it, expect } from 'vitest'
import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { renderWithProviders } from '../../test/render'
import TimelineEntry from './TimelineEntry'

describe('TimelineEntry', () => {
  it('renders title + kind icon', () => {
    renderWithProviders(
      <TimelineEntry entry={{
        id: 1, kind: 'birthday', title: 'Turned 15',
        occurred_on: '2026-04-21', metadata: {},
      }} />,
    )
    expect(screen.getByText('Turned 15')).toBeInTheDocument()
    expect(screen.getByText('🎂')).toBeInTheDocument()
  })

  it('opening entry shows EntryDetailSheet', async () => {
    const user = userEvent.setup()
    renderWithProviders(
      <TimelineEntry entry={{
        id: 1, kind: 'manual', title: 'Rode bike',
        summary: 'Big day', occurred_on: '2026-04-21', metadata: {},
      }} />,
    )
    await user.click(screen.getByRole('button', { name: /rode bike/i }))
    expect(screen.getByRole('dialog', { name: /rode bike/i })).toBeInTheDocument()
    expect(screen.getByText('Big day')).toBeInTheDocument()
  })
})
