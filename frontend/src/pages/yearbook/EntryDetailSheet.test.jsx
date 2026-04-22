import { describe, it, expect, vi } from 'vitest'
import { http, HttpResponse } from 'msw'
import { screen, waitFor, within } from '@testing-library/react'
import { renderWithProviders } from '../../test/render'
import { server } from '../../test/server'
import { buildUser, buildParent } from '../../test/factories'
import EntryDetailSheet from './EntryDetailSheet'

// Stub AnimatePresence so the modal mounts + unmounts synchronously.
vi.mock('framer-motion', async () => {
  const actual = await vi.importActual('framer-motion')
  return { ...actual, AnimatePresence: ({ children }) => children }
})

// Compute the ISO date string the component uses (local today).
function todayISO() {
  const now = new Date()
  const y = now.getFullYear()
  const m = String(now.getMonth() + 1).padStart(2, '0')
  const d = String(now.getDate()).padStart(2, '0')
  return `${y}-${m}-${d}`
}

function mountWithUser(entry, userFixture) {
  server.use(
    http.get('*/api/auth/me/', () => HttpResponse.json(userFixture)),
  )
  return renderWithProviders(
    <EntryDetailSheet entry={entry} onClose={() => {}} />,
  )
}

describe('EntryDetailSheet', () => {
  it('renders occurred_on + summary for a plain entry', () => {
    renderWithProviders(
      <EntryDetailSheet
        entry={{
          id: 1, kind: 'manual', title: 'Rode bike',
          summary: 'Big day', occurred_on: '2026-04-21', metadata: {},
        }}
        onClose={() => {}}
      />,
    )
    const dialog = screen.getByRole('dialog', { name: /rode bike/i })
    expect(within(dialog).getByText('2026-04-21')).toBeInTheDocument()
    expect(within(dialog).getByText('Big day')).toBeInTheDocument()
  })

  it("shows the 'Edit' button for the owner's same-day journal entry", async () => {
    mountWithUser(
      {
        id: 7, kind: 'journal', is_private: true,
        title: 'Today', summary: 'Wrote a story.',
        occurred_on: todayISO(), metadata: {}, user: 1,
      },
      buildUser({ id: 1 }),
    )
    await waitFor(() => {
      const dialog = screen.getByRole('dialog', { name: /today/i })
      expect(within(dialog).getByRole('button', { name: /edit/i })).toBeInTheDocument()
    })
  })

  it("hides the 'Edit' button on a prior-day entry", async () => {
    mountWithUser(
      {
        id: 8, kind: 'journal', is_private: true,
        title: 'Yesterday', summary: 'Locked now.',
        occurred_on: '2026-04-20', metadata: {}, user: 1,
      },
      buildUser({ id: 1 }),
    )
    await waitFor(() =>
      expect(screen.getByRole('dialog', { name: /yesterday/i })).toBeInTheDocument(),
    )
    expect(screen.queryByRole('button', { name: /edit/i })).not.toBeInTheDocument()
  })

  it("hides the 'Edit' button for the parent viewing a child's entry", async () => {
    mountWithUser(
      {
        id: 9, kind: 'journal', is_private: true,
        title: 'Abby today', summary: 'Her words.',
        occurred_on: todayISO(), metadata: {}, user: 1,
      },
      buildParent(),
    )
    await waitFor(() =>
      expect(screen.getByRole('dialog', { name: /abby today/i })).toBeInTheDocument(),
    )
    expect(screen.queryByRole('button', { name: /edit/i })).not.toBeInTheDocument()
  })

  it('renders the Private journal chip for parent viewers', async () => {
    mountWithUser(
      {
        id: 10, kind: 'journal', is_private: true,
        title: 'Entry', summary: 'body',
        occurred_on: todayISO(), metadata: {}, user: 1,
      },
      buildParent(),
    )
    await waitFor(() =>
      expect(screen.getByText(/Private journal/i)).toBeInTheDocument(),
    )
  })
})
