import { describe, it, expect, vi } from 'vitest'
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

import { renderWithProviders } from '../test/render'
import { spyHandler } from '../test/spy'
import { server } from '../test/server'
import CelebrationModal from './CelebrationModal'

const streakNotif = {
  id: 88,
  notification_type: 'streak_milestone',
  title: '\u{1F525} 30-day streak!',
  message: 'Keep it up!',
  is_read: false,
}

const perfectDayNotif = {
  id: 99,
  notification_type: 'perfect_day',
  title: 'Perfect Day!',
  message: 'You completed all your daily tasks. +15 coins!',
  is_read: false,
}

describe('CelebrationModal', () => {
  it('renders streak day count parsed from title', () => {
    renderWithProviders(
      <CelebrationModal notification={streakNotif} onDismiss={() => {}} />,
    )
    expect(screen.getByRole('alertdialog')).toBeInTheDocument()
    expect(screen.getByText(/30 day streak/i)).toBeInTheDocument()
  })

  it('renders perfect-day body for perfect_day type', () => {
    renderWithProviders(
      <CelebrationModal notification={perfectDayNotif} onDismiss={() => {}} />,
    )
    // The h2 carries the visible body title "Perfect day"; the sr-only
    // node mirrors the notification's "Perfect Day!" so both match a
    // case-insensitive contains. Scope to the h2 to avoid duplicates.
    expect(
      screen.getByRole('heading', { level: 2, name: /perfect day/i }),
    ).toBeInTheDocument()
    expect(screen.getByText(/\+15 coins/i)).toBeInTheDocument()
  })

  it('dismiss fires POST /api/notifications/{id}/mark_read/ and calls onDismiss', async () => {
    const spy = spyHandler(
      'post',
      /\/api\/notifications\/88\/mark_read\/?$/,
      {},
    )
    server.use(spy.handler)
    const onDismiss = vi.fn()
    const user = userEvent.setup()
    renderWithProviders(
      <CelebrationModal notification={streakNotif} onDismiss={onDismiss} />,
    )
    await user.click(screen.getByRole('button', { name: /turn the page/i }))
    await waitFor(() => expect(spy.calls).toHaveLength(1))
    expect(onDismiss).toHaveBeenCalled()
  })

  it('renders nothing for unknown notification type', () => {
    const { container } = renderWithProviders(
      <CelebrationModal
        notification={{ id: 1, notification_type: 'unknown_kind', title: 'x' }}
        onDismiss={() => {}}
      />,
    )
    expect(container.querySelector('[role="alertdialog"]')).toBeNull()
  })
})
