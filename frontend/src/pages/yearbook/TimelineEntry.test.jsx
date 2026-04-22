import { describe, it, expect, vi } from 'vitest'
import { http, HttpResponse } from 'msw'
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { renderWithProviders } from '../../test/render'
import { server } from '../../test/server'
import { buildUser, buildParent } from '../../test/factories'
import TimelineEntry from './TimelineEntry'

// Stub AnimatePresence so the EntryDetailSheet portal mounts synchronously.
vi.mock('framer-motion', async () => {
  const actual = await vi.importActual('framer-motion')
  return { ...actual, AnimatePresence: ({ children }) => children }
})

function mountAsUser(entry, userFixture) {
  server.use(
    http.get('*/api/auth/me/', () => HttpResponse.json(userFixture)),
  )
  return renderWithProviders(<TimelineEntry entry={entry} />)
}

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

  it('renders the quill glyph for journal kind', () => {
    renderWithProviders(
      <TimelineEntry entry={{
        id: 2, kind: 'journal', is_private: true, title: 'Good day',
        occurred_on: '2026-04-21', metadata: {},
      }} />,
    )
    expect(screen.getByText('🪶')).toBeInTheDocument()
  })

  it("shows the 'Private' lock chip on the parent's timeline view", async () => {
    mountAsUser(
      {
        id: 3, kind: 'journal', is_private: true, title: 'Private thought',
        occurred_on: '2026-04-21', metadata: {}, user: 1,
      },
      buildParent(),
    )
    await waitFor(() => expect(screen.getByText(/^Private$/i)).toBeInTheDocument())
  })

  it("never renders the lock chip on the child's own view", async () => {
    mountAsUser(
      {
        id: 4, kind: 'journal', is_private: true, title: 'My journal',
        occurred_on: '2026-04-21', metadata: {}, user: 1,
      },
      buildUser({ id: 1 }),
    )
    // Wait for AuthProvider to settle /auth/me/ before asserting absence.
    await waitFor(() => expect(screen.getByText('My journal')).toBeInTheDocument())
    expect(screen.queryByText(/^Private$/i)).not.toBeInTheDocument()
  })
})
