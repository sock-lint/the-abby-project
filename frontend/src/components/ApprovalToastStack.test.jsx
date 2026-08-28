import { describe, it, expect, beforeEach } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import { http, HttpResponse } from 'msw';

import { renderWithProviders } from '../test/render';
import { server } from '../test/server';
import ApprovalToastStack from './ApprovalToastStack';
import { emptyPulse } from '../test/pulseFixtures.js';
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

const approval = {
  id: 1,
  title: 'Chore approved',
  message: 'Trash taken — nice.',
  notification_type: 'chore_approved',
};

function renderStack(pulse) {
  return renderWithProviders(<ApprovalToastStack />, { pulse });
}

describe('ApprovalToastStack', () => {
  beforeEach(() => {
    localStorage.removeItem(STORAGE_KEYS.SEEN_APPROVAL_TOASTS);
  });

  it('emits a toast when a new approval arrives after the seed beat', async () => {
    server.use(http.get('*/api/auth/me/', () => HttpResponse.json(childUser)));
    const { beat } = renderStack(emptyPulse());
    // Wait for auth to resolve so the role gate opens and the seed beat lands.
    await waitFor(() => expect(screen.queryByText(/chore approved/i)).toBeNull());

    beat(emptyPulse({ notifications: [approval] }));

    await waitFor(() => expect(screen.getByText(/chore approved/i)).toBeInTheDocument());
    expect(screen.getByText(/trash taken/i)).toBeInTheDocument();
  });

  it('seeds silently — a decision already in the first beat does not toast', async () => {
    server.use(http.get('*/api/auth/me/', () => HttpResponse.json(childUser)));
    renderStack(emptyPulse({ notifications: [approval] }));
    await new Promise((r) => setTimeout(r, 50));
    expect(screen.queryByText(/chore approved/i)).toBeNull();
  });

  it('stays silent for parents (role gate)', async () => {
    server.use(http.get('*/api/auth/me/', () => HttpResponse.json(parentUser)));
    const { beat } = renderStack(emptyPulse());
    beat(emptyPulse({ notifications: [approval] }));
    await new Promise((r) => setTimeout(r, 50));
    expect(screen.queryByText(/chore approved/i)).toBeNull();
  });
});
