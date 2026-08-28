import { describe, it, expect, vi } from 'vitest'
import { fireEvent, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { delay, http, HttpResponse } from 'msw'

import { renderWithProviders } from '../test/render'
import { spyHandler } from '../test/spy'
import { server } from '../test/server'
import BirthdayCelebrationModal from './BirthdayCelebrationModal'

const entry = {
  id: 42,
  kind: 'birthday',
  title: 'Turned 15',
  occurred_on: '2026-04-21',
  chapter_year: 2025,
  metadata: { gift_coins: 1500 },
}

describe('BirthdayCelebrationModal', () => {
  it('renders age + gift and exposes role="alertdialog"', () => {
    renderWithProviders(<BirthdayCelebrationModal entry={entry} onDismiss={() => {}} />)
    expect(screen.getByRole('alertdialog', { name: /birthday/i })).toBeInTheDocument()
    expect(screen.getByText('15')).toBeInTheDocument()
    expect(screen.getByText(/1500/)).toBeInTheDocument()
  })

  it('dismiss fires POST /api/chronicle/{id}/mark-viewed/ then onDismiss', async () => {
    const spy = spyHandler('post', /\/api\/chronicle\/42\/mark-viewed\/?$/, {})
    server.use(spy.handler)
    const onDismiss = vi.fn()
    const user = userEvent.setup()
    renderWithProviders(<BirthdayCelebrationModal entry={entry} onDismiss={onDismiss} />)
    await user.click(screen.getByRole('button', { name: /turn the page/i }))
    await waitFor(() => expect(spy.calls).toHaveLength(1))
    expect(onDismiss).toHaveBeenCalled()
  })

  // The streak/perfect-day celebration closes on a tap outside the card, and
  // a kid trained by that one taps the wash here too.
  it('dismisses on a tap outside the card', () => {
    const onDismiss = vi.fn()
    renderWithProviders(<BirthdayCelebrationModal entry={entry} onDismiss={onDismiss} />)
    const wash = screen.getByRole('alertdialog').firstChild
    fireEvent.click(wash)
    expect(onDismiss).toHaveBeenCalled()
  })

  it('does not dismiss on a tap inside the card', () => {
    const onDismiss = vi.fn()
    renderWithProviders(<BirthdayCelebrationModal entry={entry} onDismiss={onDismiss} />)
    fireEvent.click(screen.getByRole('heading', { level: 2 }))
    expect(onDismiss).not.toHaveBeenCalled()
  })

  // The overlay covers the whole app — it must never wait on the network to
  // let go of the screen.
  it('closes immediately even when mark-viewed never responds', async () => {
    server.use(
      http.post(/\/chronicle\/42\/mark-viewed/, async () => {
        await delay('infinite')
        return HttpResponse.json({})
      }),
    )
    const onDismiss = vi.fn()
    const user = userEvent.setup()
    renderWithProviders(<BirthdayCelebrationModal entry={entry} onDismiss={onDismiss} />)
    await user.click(screen.getByRole('button', { name: /turn the page/i }))
    expect(onDismiss).toHaveBeenCalled()
  })

  it('respects prefers-reduced-motion by skipping confetti', () => {
    Object.defineProperty(window, 'matchMedia', {
      writable: true,
      value: vi.fn().mockImplementation((query) => ({
        matches: query.includes('reduce'),
        media: query,
        onchange: null,
        addListener: vi.fn(),
        removeListener: vi.fn(),
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
        dispatchEvent: vi.fn(),
      })),
    })
    renderWithProviders(<BirthdayCelebrationModal entry={entry} onDismiss={() => {}} />)
    expect(screen.queryByTestId('birthday-confetti')).toBeNull()
  })
})
