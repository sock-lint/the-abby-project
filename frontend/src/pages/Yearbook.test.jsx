import { describe, it, expect } from 'vitest'
import { screen } from '@testing-library/react'
import { http, HttpResponse } from 'msw'

import { renderWithProviders } from '../test/render'
import { server } from '../test/server'
import { buildUser } from '../test/factories'
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
