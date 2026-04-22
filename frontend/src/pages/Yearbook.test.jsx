import { describe, it, expect } from 'vitest'
import { screen, waitFor } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import userEvent from '@testing-library/user-event'

import { renderWithProviders } from '../test/render'
import { server } from '../test/server'
import { buildUser, buildParent } from '../test/factories'
import { spyHandler } from '../test/spy'
import Yearbook from './Yearbook'

describe('Yearbook page', () => {
  it('shows empty-state when DOB missing', async () => {
    const child = buildUser({ role: 'child', date_of_birth: null })
    server.use(
      http.get('*/api/auth/me/', () => HttpResponse.json(child)),
      http.get('*/api/chronicle/summary/', () =>
        HttpResponse.json({ chapters: [], current_chapter_year: 2025 }),
      ),
    )
    renderWithProviders(<Yearbook />)
    expect(await screen.findByText(/set your date of birth/i)).toBeInTheDocument()
  })

  it('renders chapter cards from summary payload', async () => {
    const child = buildUser({ role: 'child', date_of_birth: '2011-09-22' })
    server.use(
      http.get('*/api/auth/me/', () => HttpResponse.json(child)),
      http.get('*/api/chronicle/summary/', () =>
        HttpResponse.json({
          chapters: [
            { chapter_year: 2025, grade: 9, label: 'Freshman Year', is_current: true, is_post_hs: false, stats: {}, entries: [] },
            { chapter_year: 2024, grade: 8, label: 'Grade 8', is_current: false, is_post_hs: false, stats: { projects_completed: 5 }, entries: [] },
          ],
          current_chapter_year: 2025,
        }),
      ),
    )
    renderWithProviders(<Yearbook />)
    expect(await screen.findByText('Freshman Year')).toBeInTheDocument()
    expect(await screen.findByText('Grade 8')).toBeInTheDocument()
  })
})

describe('Yearbook — parent add-memory interaction', () => {
  it('submitting ManualEntryFormModal POSTs /api/chronicle/manual/ with expected body', async () => {
    const parent = buildParent()
    server.use(
      http.get('*/api/auth/me/', () => HttpResponse.json(parent)),
      http.get('*/api/chronicle/summary/', () =>
        HttpResponse.json({
          chapters: [
            { chapter_year: 2025, grade: 9, label: 'Freshman Year', is_current: true, is_post_hs: false, stats: {}, entries: [] },
          ],
          current_chapter_year: 2025,
        }),
      ),
    )
    const spy = spyHandler('post', /\/api\/chronicle\/manual\/$/, { id: 99 })
    server.use(spy.handler)

    const user = userEvent.setup()
    renderWithProviders(<Yearbook />)

    await user.click(await screen.findByRole('button', { name: /add memory/i }))

    await user.type(await screen.findByLabelText(/title/i), 'Rode a bike')
    await user.type(screen.getByLabelText(/when/i), '2026-04-21')
    await user.click(screen.getByRole('button', { name: /save/i }))

    await waitFor(() => expect(spy.calls).toHaveLength(1))
    expect(spy.calls[0].body).toMatchObject({
      title: 'Rode a bike',
      occurred_on: '2026-04-21',
    })
  })

  it('child does not see Add memory button', async () => {
    const child = buildUser({ role: 'child', date_of_birth: '2011-09-22' })
    server.use(
      http.get('*/api/auth/me/', () => HttpResponse.json(child)),
      http.get('*/api/chronicle/summary/', () =>
        HttpResponse.json({ chapters: [], current_chapter_year: 2025 }),
      ),
    )
    renderWithProviders(<Yearbook />)
    await screen.findByRole('generic') // wait for render to settle
    expect(screen.queryByRole('button', { name: /add memory/i })).toBeNull()
  })
})
