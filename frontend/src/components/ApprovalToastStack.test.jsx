import { describe, it, expect, beforeEach, vi } from 'vitest';
import { screen, waitFor, act } from '@testing-library/react';
import { http, HttpResponse } from 'msw';

import { renderWithProviders } from '../test/render';
import { server } from '../test/server';
import ApprovalToastStack from './ApprovalToastStack';
import { STORAGE_KEYS } from '../constants/storage';

const childUser = {
  id: 7,
  username: 'kid',
  display_name: 'Kid',
  role: 'child',
  family: { id: 1, name: 'Test Family' },
};

const parentUser = {
  id: 1,
  username: 'mom',
  display_name: 'Mom',
  role: 'parent',
  family: { id: 1, name: 'Test Family' },
};

describe('ApprovalToastStack', () => {
  beforeEach(() => {
    localStorage.removeItem(STORAGE_KEYS.SEEN_APPROVAL_TOASTS);
  });

  it('emits a toast when a new chore_approved notification arrives', async () => {
    let callCount = 0;
    server.use(
      http.get('*/api/auth/me/', () => HttpResponse.json(childUser)),
      http.get(/\/api\/notifications\/$/, () => {
        callCount += 1;
        if (callCount === 1) return HttpResponse.json([]);
        return HttpResponse.json([
          {
            id: 1,
            title: 'Chore approved',
            message: 'Trash taken — nice.',
            notification_type: 'chore_approved',
          },
        ]);
      }),
    );

    vi.useFakeTimers({ shouldAdvanceTime: true });
    try {
      renderWithProviders(<ApprovalToastStack />);
      // Wait for the seed call (after auth resolves).
      await waitFor(() => expect(callCount).toBeGreaterThanOrEqual(1));
      await act(async () => {
        vi.advanceTimersByTime(31_000);
      });
      await waitFor(() => {
        expect(screen.getByText(/chore approved/i)).toBeInTheDocument();
      });
      expect(screen.getByText(/trash taken/i)).toBeInTheDocument();
    } finally {
      vi.useRealTimers();
    }
  });

  it('does not poll for parents (role gate)', async () => {
    let calls = 0;
    server.use(
      http.get('*/api/auth/me/', () => HttpResponse.json(parentUser)),
      http.get(/\/api\/notifications\/$/, () => {
        calls += 1;
        return HttpResponse.json([]);
      }),
    );
    renderWithProviders(<ApprovalToastStack />);
    await new Promise((r) => setTimeout(r, 50));
    expect(calls).toBe(0);
  });
});
