import { describe, expect, it } from 'vitest';
import { http, HttpResponse } from 'msw';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import Manage from './Manage.jsx';
import { AuthProvider } from '../hooks/useApi.js';
import { server } from '../test/server.js';
import { buildParent } from '../test/factories.js';
import { spyHandler } from '../test/spy.js';

const applications = [
  { client_id: 'synthetic-client-1', name: 'Codex attempt 1' },
  { client_id: 'synthetic-client-2', name: 'Codex attempt 2' },
];
const accessToken = {
  id: 17,
  application_name: 'Codex attempt 2',
  application_client_id: 'synthetic-client-2',
  scope: 'mcp:catalog',
  expires_at: '2099-01-01T00:00:00Z',
};

function renderOAuthManagement(tokens = []) {
  server.use(
    http.get('*/api/auth/me/', () => HttpResponse.json(buildParent({ is_staff: true }))),
    http.get('*/api/admin/families/', () => HttpResponse.json({ ok: true })),
    http.get('*/api/admin/oauth/applications/', () => HttpResponse.json({ applications })),
    http.get('*/api/admin/oauth/tokens/', () => HttpResponse.json({ tokens })),
  );
  return render(
    <MemoryRouter initialEntries={['/manage?tab=Admin']}>
      <AuthProvider><Manage /></AuthProvider>
    </MemoryRouter>,
  );
}

describe('Manage — OAuth clients', () => {
  it('shows incomplete registrations separately from the current account’s empty access-token list', async () => {
    renderOAuthManagement();

    expect(await screen.findByText(/registration happens before sign-in.*does not confirm/i)).toBeVisible();
    const registered = screen.getByRole('region', { name: 'Registered clients' });
    expect(within(registered).getByRole('heading', { name: 'Registered clients (2)' })).toBeVisible();
    expect(within(registered).getByText('Codex attempt 1')).toBeVisible();
    expect(within(registered).getByText('Codex attempt 2')).toBeVisible();
    expect(within(registered).getByText(/registration happens before sign-in.*does not confirm/i)).toBeVisible();

    const active = screen.getByRole('region', { name: 'Your active access tokens' });
    expect(within(active).getByRole('heading', { name: 'Your active access tokens (0)' })).toBeVisible();
    expect(within(active).getByText(/no unexpired access tokens.*your abby account/i)).toBeVisible();
    expect(within(active).getByText(/unfinished.*expired.*revoked/i)).toBeVisible();
    expect(within(active).queryByRole('list')).not.toBeInTheDocument();
    expect(screen.getByText(/confirm success in the codex terminal.*authenticated tool/i)).toBeVisible();
  });

  it('shows only the returned current-account tokens as authorization evidence and preserves their scopes', async () => {
    renderOAuthManagement([accessToken]);

    const active = await screen.findByRole('region', { name: 'Your active access tokens' });
    expect(within(active).getByRole('heading', { name: 'Your active access tokens (1)' })).toBeVisible();
    expect(within(active).getByText('Codex attempt 2')).toBeVisible();
    expect(within(active).queryByText('Codex attempt 1')).not.toBeInTheDocument();
    expect(within(active).getByText('mcp:catalog')).toBeVisible();
    expect(within(active).getByText(/issued to your abby account/i)).toBeVisible();
    expect(within(active).queryByText(/no unexpired access tokens/i)).not.toBeInTheDocument();
  });

  it('does not report an empty authorization list when loading fails and can retry the read', async () => {
    const user = userEvent.setup();
    let unavailable = true;
    renderOAuthManagement();
    const tokens = spyHandler('get', /\/api\/admin\/oauth\/tokens\/$/, () => unavailable
      ? HttpResponse.json({ detail: 'Unable to load authorizations.' }, { status: 503 })
      : HttpResponse.json({ tokens: [accessToken] }));
    server.use(tokens.handler);

    expect(await screen.findByText('Unable to load authorizations.')).toBeVisible();
    expect(screen.queryByText(/don't have any active oauth tokens/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/no unexpired access tokens/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/no oauth clients have registered/i)).not.toBeInTheDocument();
    unavailable = false;
    await user.click(screen.getByRole('button', { name: 'Try again' }));
    expect(await screen.findByRole('heading', { name: 'Your active access tokens (1)' })).toBeVisible();
    expect(tokens.calls).toHaveLength(2);
    expect(tokens.calls[1].url).toMatch(/\/api\/admin\/oauth\/tokens\/$/);
  });

  it('keeps OAuth management unavailable when the staff-parent probe refuses access', async () => {
    renderOAuthManagement();
    const probe = spyHandler('get', /\/api\/admin\/families\/$/, HttpResponse.json({ detail: 'Not authorized.' }, { status: 403 }));
    const applicationsRead = spyHandler('get', /\/api\/admin\/oauth\/applications\/$/, { applications });
    const tokensRead = spyHandler('get', /\/api\/admin\/oauth\/tokens\/$/, { tokens: [accessToken] });
    server.use(probe.handler, applicationsRead.handler, tokensRead.handler);

    await waitFor(() => expect(probe.calls).toHaveLength(1));
    expect(screen.queryByRole('tab', { name: 'Admin' })).not.toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'OAuth clients' })).not.toBeInTheDocument();
    expect(applicationsRead.calls).toHaveLength(0);
    expect(tokensRead.calls).toHaveLength(0);
  });

  it('confirms and revokes only the selected current-account access token', async () => {
    const user = userEvent.setup();
    renderOAuthManagement([accessToken]);
    const revoke = spyHandler('delete', /\/api\/admin\/oauth\/tokens\/17\/$/, { ok: true });
    server.use(revoke.handler);

    const active = await screen.findByRole('region', { name: 'Your active access tokens' });
    await user.click(within(active).getByRole('button', { name: 'Revoke' }));
    expect(revoke.calls).toHaveLength(0);
    const dialog = await screen.findByRole('alertdialog');
    await user.click(within(dialog).getByRole('button', { name: 'Revoke' }));
    await waitFor(() => expect(revoke.calls).toHaveLength(1));
    expect(revoke.calls[0]).toMatchObject({ method: 'DELETE', body: null });
    expect(revoke.calls[0].url).toMatch(/\/api\/admin\/oauth\/tokens\/17\/$/);
  });

  it('explains that revoking a registration’s tokens affects every user and sends the selected client ID', async () => {
    const user = userEvent.setup();
    renderOAuthManagement([accessToken]);
    const revoke = spyHandler('delete', /\/api\/admin\/oauth\/applications\/synthetic-client-1\/tokens\/$/, { ok: true });
    server.use(revoke.handler);

    const registered = await screen.findByRole('region', { name: 'Registered clients' });
    const row = within(registered).getByText('Codex attempt 1').closest('li');
    await user.click(within(row).getByRole('button', { name: 'Revoke all tokens' }));
    expect(revoke.calls).toHaveLength(0);
    const dialog = await screen.findByRole('alertdialog');
    expect(within(dialog).getByText(/every user/i)).toBeVisible();
    await user.click(within(dialog).getByRole('button', { name: 'Revoke' }));
    await waitFor(() => expect(revoke.calls).toHaveLength(1));
    expect(revoke.calls[0]).toMatchObject({ method: 'DELETE', body: null });
    expect(revoke.calls[0].url).toMatch(/\/api\/admin\/oauth\/applications\/synthetic-client-1\/tokens\/$/);
  });
});
