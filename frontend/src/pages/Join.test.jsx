import { describe, expect, it, vi } from 'vitest';
import { http, HttpResponse } from 'msw';
import { screen, waitFor } from '@testing-library/react';
import { renderWithProviders, userEvent } from '../test/render.jsx';
import { server } from '../test/server.js';
import { spyHandler } from '../test/spy.js';
import { joinFamily } from '../api';
import Join from './Join.jsx';

function renderJoin(onJoin = vi.fn(), handlers = []) {
  server.use(...handlers);
  return renderWithProviders(<Join onJoin={onJoin} />, {
    route: '/join/tok123',
    routePath: '/join/:token',
  });
}

describe('Join', () => {
  it('previews whose family the invite opens', async () => {
    renderJoin(vi.fn(), [
      http.get('*/api/auth/join/tok123/', () =>
        HttpResponse.json({
          family_name: 'The Sageb Family', invited_by: 'Sage', expires_at: '',
        }),
      ),
    ]);
    await waitFor(() =>
      expect(screen.getByText(/the sageb family/i)).toBeInTheDocument(),
    );
    expect(screen.getByText(/sage invited you/i)).toBeInTheDocument();
  });

  it('shows the sealed state for an invalid or expired token', async () => {
    renderJoin(vi.fn(), [
      http.get('*/api/auth/join/tok123/', () =>
        HttpResponse.json(
          { error: 'This invite link is invalid or has expired.' },
          { status: 404 },
        ),
      ),
    ]);
    await waitFor(() =>
      expect(screen.getByText(/this invite is sealed/i)).toBeInTheDocument(),
    );
    expect(screen.queryByRole('button', { name: /join the family/i })).toBeNull();
  });

  it('submitting posts credentials to the join endpoint', async () => {
    const user = userEvent.setup();
    const join = spyHandler('post', /\/api\/auth\/join\/tok123\/$/, {
      token: 'k', user: { id: 9, role: 'parent' }, family: {},
    });
    renderJoin((token, payload) => joinFamily(token, payload), [
      http.get('*/api/auth/join/tok123/', () =>
        HttpResponse.json({ family_name: 'Sageb', invited_by: 'Sage', expires_at: '' }),
      ),
      join.handler,
    ]);

    await screen.findByRole('button', { name: /join the family/i });
    await user.type(screen.getByLabelText(/your name/i), 'Robin');
    await user.type(screen.getByLabelText(/sign-in name/i), 'robin');
    await user.type(screen.getByLabelText(/secret word/i), 'sturdy-pass-9');
    await user.click(screen.getByRole('button', { name: /join the family/i }));

    await waitFor(() => expect(join.calls).toHaveLength(1));
    expect(join.calls[0].body).toEqual({
      username: 'robin', password: 'sturdy-pass-9', display_name: 'Robin',
    });
  });

  it('surfaces a validation error from the server', async () => {
    const user = userEvent.setup();
    renderJoin(
      (token, payload) => joinFamily(token, payload),
      [
        http.get('*/api/auth/join/tok123/', () =>
          HttpResponse.json({ family_name: 'Sageb', invited_by: 'Sage', expires_at: '' }),
        ),
        http.post('*/api/auth/join/tok123/', () =>
          HttpResponse.json({ error: 'Username is already taken.' }, { status: 400 }),
        ),
      ],
    );

    await screen.findByRole('button', { name: /join the family/i });
    await user.type(screen.getByLabelText(/sign-in name/i), 'robin');
    await user.type(screen.getByLabelText(/secret word/i), 'sturdy-pass-9');
    await user.click(screen.getByRole('button', { name: /join the family/i }));

    await waitFor(() =>
      expect(screen.getByText(/username is already taken/i)).toBeInTheDocument(),
    );
  });
});
