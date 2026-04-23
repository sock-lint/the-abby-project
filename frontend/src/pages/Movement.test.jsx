import { describe, expect, it } from 'vitest';
import { http, HttpResponse } from 'msw';
import { renderWithProviders, screen, waitFor } from '../test/render';
import { server } from '../test/server';
import { spyHandler } from '../test/spy';
import { buildUser, buildParent } from '../test/factories';
import Movement from './Movement';

const RUN = {
  id: 1, name: 'Run', icon: '🏃', slug: 'run',
  default_intensity: 'medium', is_active: true, order: 0, skill_tags: [],
};

function stubTypes() {
  server.use(
    http.get('*/api/movement-types/', () => HttpResponse.json([RUN])),
  );
}

function stubMe(user) {
  server.use(
    http.get('*/api/auth/me/', () => HttpResponse.json(user)),
  );
  // Drop a token so AuthProvider boots into the authed branch.
  localStorage.setItem('abby_auth_token', 'test-token');
}

describe('Movement page', () => {
  it('shows the empty state when nothing logged today', async () => {
    stubTypes();
    server.use(
      http.get('*/api/movement-sessions/', () => HttpResponse.json([])),
    );
    stubMe(buildUser());
    renderWithProviders(<Movement />);
    expect(await screen.findByText(/Nothing logged yet today/i)).toBeInTheDocument();
  });

  it('lists today’s sessions in the Today section', async () => {
    stubTypes();
    const today = new Date().toISOString().slice(0, 10);
    server.use(
      http.get('*/api/movement-sessions/', () =>
        HttpResponse.json([
          {
            id: 11, user: 1,
            movement_type: 1, movement_type_name: 'Run', movement_type_icon: '🏃',
            duration_minutes: 30, intensity: 'medium',
            occurred_on: today, notes: 'felt good',
            xp_awarded: 15, created_at: '2026-04-23T15:00:00Z',
          },
        ]),
      ),
    );
    stubMe(buildUser({ id: 1 }));
    renderWithProviders(<Movement />);
    expect(await screen.findByText('Run')).toBeInTheDocument();
    expect(screen.getByText(/felt good/i)).toBeInTheDocument();
    expect(screen.getByText(/\+15 XP/)).toBeInTheDocument();
    expect(screen.getByText(/medium/i)).toBeInTheDocument();
  });

  it('a child sees a "Log" button; parent does not', async () => {
    stubTypes();
    server.use(
      http.get('*/api/movement-sessions/', () => HttpResponse.json([])),
    );
    stubMe(buildUser());
    const { unmount } = renderWithProviders(<Movement />);
    expect(await screen.findByRole('button', { name: /^Log$/i })).toBeInTheDocument();
    unmount();
    stubMe(buildParent());
    renderWithProviders(<Movement />);
    expect(await screen.findByText(/Movement/)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /^Log$/i })).not.toBeInTheDocument();
  });

  it('opens the log modal and POSTs a session when "Log" is tapped', async () => {
    stubTypes();
    server.use(
      http.get('*/api/movement-sessions/', () => HttpResponse.json([])),
    );
    const spy = spyHandler('post', /\/api\/movement-sessions\/$/, { id: 99 });
    server.use(spy.handler);

    stubMe(buildUser());
    const { user } = renderWithProviders(<Movement />);

    await user.click(await screen.findByRole('button', { name: /^Log$/i }));

    await waitFor(() => {
      expect(screen.getByRole('combobox', { name: /what did you do/i })).not.toBeDisabled();
    });

    await user.selectOptions(
      screen.getByRole('combobox', { name: /what did you do/i }),
      '1',
    );
    await user.click(screen.getByRole('button', { name: /log session/i }));

    await waitFor(() => expect(spy.calls).toHaveLength(1));
    expect(spy.calls[0].body).toMatchObject({
      movement_type_id: 1,
      duration_minutes: 30,
    });
  });
});
