import { act, screen, waitFor, within } from '@testing-library/react';
import { HttpResponse, http } from 'msw';
import { describe, expect, it, vi } from 'vitest';
import Manage from '../Manage';
import { useAuth } from '../../hooks/useApi';
import { buildParent, buildUser } from '../../test/factories';
import { renderWithProviders } from '../../test/render';
import { server } from '../../test/server';
import { spyHandler } from '../../test/spy';

vi.mock('framer-motion', async () => {
  const original = await vi.importActual('framer-motion');
  return { ...original, AnimatePresence: ({ children }) => children };
});

function roster(kind = 'child') {
  const actor = buildParent({ family: { id: 1 } });
  const member = buildUser({
    id: 7, username: 'robin', display_name: 'Robin', role: kind, is_active: true,
  });
  const endpoint = kind === 'child' ? 'children' : 'parents';
  let deleted = false;
  server.use(
    http.get('*/api/auth/me/', () => HttpResponse.json(actor)),
    http.get(`*/api/${endpoint}/`, () => HttpResponse.json(deleted ? [] : [member])),
  );
  return { endpoint, deleted: () => { deleted = true; } };
}

async function openConfirmation(user) {
  await user.click(await screen.findByRole('button', { name: 'Edit' }));
  const edit = await screen.findByRole('dialog', { name: 'Edit Robin' });
  await user.click(within(edit).getByRole('button', { name: 'Delete account' }));
  return screen.findByRole('dialog', { name: "Delete Robin's account?" });
}

function deferred() {
  let resolve;
  const promise = new Promise((complete) => { resolve = complete; });
  return { promise, resolve };
}

function deletionResponse() {
  return new Promise((resolve) => {
    const onResponse = ({ request }) => {
      if (request.method === 'DELETE' && new URL(request.url).pathname === '/api/children/7/') {
        server.events.removeListener('response:mocked', onResponse);
        resolve();
      }
    };
    server.events.on('response:mocked', onResponse);
  });
}

function AccountSwitcher() {
  const { setUser } = useAuth();
  return <>
    <button type="button" onClick={() => {
      localStorage.setItem('abby_auth_token', 'replacement-session');
      setUser(buildParent({ id: 100, family: { id: 2 } }));
    }}>Switch family account</button>
    <Manage />
  </>;
}

describe('Family member account deletion', () => {
  it('explains deletion and retained copies, and cancellation sends no request', async () => {
    roster();
    const deletion = spyHandler('delete', /\/api\/children\/7\/$/, new HttpResponse(null, { status: 204 }));
    server.use(deletion.handler);
    const { user } = renderWithProviders(<Manage />, { route: '/manage' });
    const dialog = await openConfirmation(user);
    expect(dialog).toHaveTextContent(/projects and homework they created or were assigned/i);
    expect(dialog).toHaveTextContent(/private journal/i);
    expect(dialog).toHaveTextContent(/other family members.*name/i);
    expect(dialog).toHaveTextContent(/files.*retries/i);
    expect(dialog).toHaveTextContent(/backups.*provider/i);
    await user.type(within(dialog).getByLabelText('Type to confirm'), 'delete robin');
    await user.click(within(dialog).getByRole('button', { name: 'Cancel' }));
    expect(screen.queryByRole('dialog', { name: "Delete Robin's account?" })).toBeNull();
    expect(screen.getByRole('dialog', { name: 'Edit Robin' })).toBeInTheDocument();
    expect(deletion.calls).toHaveLength(0);
    await user.click(within(screen.getByRole('dialog', { name: 'Edit Robin' })).getByRole('button', { name: 'Delete account' }));
    expect(screen.getByLabelText('Type to confirm')).toHaveValue('');
  });

  it.each(['child', 'parent'])('deletes a %s only after matching confirmation and refreshes its roster', async (kind) => {
    const state = roster(kind);
    const deletion = spyHandler('delete', new RegExp(`/api/${state.endpoint}/7/$`), () => {
      state.deleted();
      return new HttpResponse(null, { status: 204 });
    });
    server.use(deletion.handler);
    const { user } = renderWithProviders(<Manage />, { route: kind === 'child' ? '/manage' : '/manage?tab=Family' });
    const dialog = await openConfirmation(user);
    const confirm = within(dialog).getByRole('button', { name: 'Delete account' });
    await user.type(within(dialog).getByLabelText('Type to confirm'), 'wrong');
    expect(confirm).toBeDisabled();
    expect(deletion.calls).toHaveLength(0);
    await user.clear(within(dialog).getByLabelText('Type to confirm'));
    await user.type(within(dialog).getByLabelText('Type to confirm'), 'delete robin');
    await user.click(confirm);
    await waitFor(() => expect(deletion.calls).toHaveLength(1));
    expect(deletion.calls[0]).toMatchObject({ method: 'DELETE', body: null });
    expect(deletion.calls[0].url).toMatch(new RegExp(`/api/${state.endpoint}/7/$`));
    await waitFor(() => expect(screen.queryByText('@robin')).toBeNull());
    expect(screen.queryByRole('dialog', { name: 'Edit Robin' })).toBeNull();
  });

  it('retains the confirmation after a server failure and supports a deliberate retry', async () => {
    const state = roster();
    let attempts = 0;
    const deletion = spyHandler('delete', /\/api\/children\/7\/$/, () => {
      if (++attempts === 1) return HttpResponse.json({ error: 'Storage queue unavailable.' }, { status: 503 });
      state.deleted();
      return new HttpResponse(null, { status: 204 });
    });
    server.use(deletion.handler);
    const { user } = renderWithProviders(<Manage />, { route: '/manage' });
    const dialog = await openConfirmation(user);
    await user.type(within(dialog).getByLabelText('Type to confirm'), 'delete robin');
    await user.click(within(dialog).getByRole('button', { name: 'Delete account' }));
    expect(await within(dialog).findByRole('alert')).toHaveTextContent(/could not confirm deletion/i);
    expect(within(dialog).getByLabelText('Type to confirm')).toHaveValue('delete robin');
    await user.click(within(dialog).getByRole('button', { name: 'Delete account' }));
    await waitFor(() => expect(deletion.calls).toHaveLength(2));
    expect(deletion.calls.every(({ method, body }) => method === 'DELETE' && body === null)).toBe(true);
    await waitFor(() => expect(screen.queryByRole('dialog', { name: 'Edit Robin' })).toBeNull());
  });

  it('shows a permission refusal without removing the member or exposing another account', async () => {
    roster();
    const deletion = spyHandler('delete', /\/api\/children\/7\/$/,
      HttpResponse.json({ error: 'You do not have permission to perform this action.' }, { status: 403 }));
    server.use(deletion.handler);
    const { user } = renderWithProviders(<Manage />, { route: '/manage' });
    const dialog = await openConfirmation(user);
    await user.type(within(dialog).getByLabelText('Type to confirm'), 'delete robin');
    await user.click(within(dialog).getByRole('button', { name: 'Delete account' }));
    expect(await within(dialog).findByRole('alert')).toHaveTextContent('You do not have permission');
    expect(within(dialog).getByRole('button', { name: 'Delete account' })).toBeEnabled();
    expect(screen.getByText('@robin')).toBeInTheDocument();
    expect(deletion.calls).toHaveLength(1);
    expect(deletion.calls[0]).toMatchObject({ method: 'DELETE', body: null });
    expect(deletion.calls[0].url).toMatch(/\/api\/children\/7\/$/);
  });

  it('blocks repeated confirmation and dismissal while the deletion is in flight', async () => {
    const state = roster();
    const pending = deferred();
    const deletion = spyHandler('delete', /\/api\/children\/7\/$/, async () => {
      await pending.promise;
      state.deleted();
      return new HttpResponse(null, { status: 204 });
    });
    server.use(deletion.handler);
    const { user } = renderWithProviders(<Manage />, { route: '/manage' });
    const dialog = await openConfirmation(user);
    await user.type(within(dialog).getByLabelText('Type to confirm'), 'delete robin');
    try {
      await user.dblClick(within(dialog).getByRole('button', { name: 'Delete account' }));
      await waitFor(() => expect(deletion.calls).toHaveLength(1));
      expect(within(dialog).getByRole('button', { name: 'Deleting…' })).toBeDisabled();
      expect(within(dialog).getByRole('button', { name: 'Cancel' })).toBeDisabled();
      await user.keyboard('{Escape}');
      expect(screen.getByRole('dialog', { name: "Delete Robin's account?" })).toBeInTheDocument();
    } finally {
      await act(async () => { pending.resolve(); });
    }
    await waitFor(() => expect(screen.queryByRole('dialog', { name: 'Edit Robin' })).toBeNull());
  });

  it.each([204, 503])('ignores a delayed %s deletion response after switching family accounts', async (status) => {
    roster();
    const pending = deferred();
    const deletion = spyHandler('delete', /\/api\/children\/7\/$/, async () => {
      await pending.promise;
      return status === 204 ? new HttpResponse(null, { status })
        : HttpResponse.json({ error: 'Previous family failure.' }, { status });
    });
    server.use(deletion.handler);
    const { user } = renderWithProviders(<AccountSwitcher />, { route: '/manage' });
    const dialog = await openConfirmation(user);
    await user.type(within(dialog).getByLabelText('Type to confirm'), 'delete robin');
    await user.click(within(dialog).getByRole('button', { name: 'Delete account' }));
    await waitFor(() => expect(deletion.calls).toHaveLength(1));
    server.use(http.get('*/api/children/', () => HttpResponse.json([
      buildUser({ id: 8, display_name: 'New family child' }),
    ])));
    await user.click(screen.getByRole('button', { name: 'Switch family account' }));
    await user.click(await screen.findByRole('button', { name: 'Edit' }));
    const currentEdit = await screen.findByRole('dialog', { name: 'Edit New family child' });
    const completed = deletionResponse();
    await act(async () => { pending.resolve(); await completed; });
    expect(currentEdit).toBeInTheDocument();
    expect(screen.queryByText('Previous family failure.')).toBeNull();
    expect(screen.queryByRole('dialog', { name: "Delete Robin's account?" })).toBeNull();
    expect(screen.queryByDisplayValue('delete robin')).toBeNull();
    expect(deletion.calls).toHaveLength(1);
  });

  it('does not refresh or claim deletion when its credential changed before the response', async () => {
    roster();
    const pending = deferred();
    const reads = vi.fn();
    server.use(http.get('*/api/children/', ({ request }) => {
      reads(request.headers.get('Authorization'));
      return HttpResponse.json([buildUser({ id: 7, username: 'robin', display_name: 'Robin' })]);
    }));
    const deletion = spyHandler('delete', /\/api\/children\/7\/$/, async () => {
      await pending.promise;
      return new HttpResponse(null, { status: 204 });
    });
    server.use(deletion.handler);
    const { user } = renderWithProviders(<Manage />, { route: '/manage' });
    const dialog = await openConfirmation(user);
    await user.type(within(dialog).getByLabelText('Type to confirm'), 'delete robin');
    await user.click(within(dialog).getByRole('button', { name: 'Delete account' }));
    await waitFor(() => expect(deletion.calls).toHaveLength(1));
    // A response may beat the auth provider's next render after storage changes.
    localStorage.setItem('abby_auth_token', 'replacement-session');
    const completed = deletionResponse();
    await act(async () => { pending.resolve(); await completed; });
    expect(reads).toHaveBeenCalledTimes(1);
    expect(reads).toHaveBeenCalledWith('Token test-session');
    expect(screen.getByRole('dialog', { name: "Delete Robin's account?" })).toBeInTheDocument();
    expect(deletion.calls).toHaveLength(1);
  });
});
