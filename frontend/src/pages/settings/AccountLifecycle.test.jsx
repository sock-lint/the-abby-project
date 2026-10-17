import { act, screen, waitFor, within } from '@testing-library/react';
import { http, HttpResponse } from 'msw';
import { describe, expect, it, vi } from 'vitest';
import AccountLifecycle from './AccountLifecycle';
import SettingsPage from '../SettingsPage';
import { useAuth } from '../../hooks/useApi';
import { buildParent, buildUser } from '../../test/factories';
import { renderWithProviders } from '../../test/render';
import { selectDropdown } from '../../test/selectDropdown';
import { spyHandler } from '../../test/spy';
import { server } from '../../test/server';

vi.mock('framer-motion', async () => {
  const original = await vi.importActual('framer-motion');
  return { ...original, AnimatePresence: ({ children }) => children };
});

const PASSWORD = 'synthetic-current-password';
const actor = (over = {}) => buildParent({ id: 99, username: 'parent', family: { id: 1, name: 'Our family', slug: 'our-family' }, ...over });
function preview(over = {}) {
  return {
    user: { id: 99, username: 'parent' },
    family: { id: 1, name: 'Our family', slug: 'our-family', primary_parent_id: 99 },
    family_version: 'a'.repeat(64),
    family_members: { parents: 2, children: 3 },
    successors: [{ id: 100, display_name: 'Other parent' }],
    shared_work: { projects: 2, project_templates: 1, homework_assignments: 3, homework_templates: 0, chores: 1, habits: 2 },
    can_delete_account: true, can_close_family: false,
    ...over,
  };
}
function seed(data = preview(), user = actor()) {
  server.use(
    http.get('*/api/auth/me/', () => HttpResponse.json(user)),
    http.get('*/api/account/lifecycle/', () => HttpResponse.json(data)),
  );
}
function SessionHarness() {
  const { user, setUser } = useAuth();
  return <>
    <p>{user ? `Signed in: ${user.username}` : 'Signed out'}</p>
    <button onClick={() => {
      localStorage.setItem('abby_auth_token', 'replacement-session');
      setUser(actor({ id: 200, username: 'replacement', family: { id: 2, name: 'New family', slug: 'new-family' } }));
    }}>Switch account</button>
    <button onClick={() => setUser((current) => ({ ...current, theme: 'vigil' }))}>Update current profile</button>
    <AccountLifecycle />
  </>;
}
async function open(user, kind) {
  const trigger = kind === 'transfer' ? 'Transfer family contact' : kind === 'close' ? 'Close family' : 'Delete my account';
  await user.click(await screen.findByRole('button', { name: trigger, exact: true }));
  return screen.findByRole('dialog', { name: kind === 'transfer' ? 'Transfer family contact' : kind === 'close' ? 'Close Our family?' : 'Delete my account?' });
}
async function fill(user, dialog, kind, isChild = false) {
  if (kind === 'transfer' || (kind === 'delete' && !isChild)) {
    await selectDropdown(user, within(dialog).getByRole('combobox'), 'Other parent');
  }
  await user.type(within(dialog).getByLabelText('Current password'), PASSWORD);
  if (kind !== 'transfer') {
    await user.type(within(dialog).getByLabelText(kind === 'close' ? 'Type the family identifier to confirm' : 'Type your username to confirm'), kind === 'close' ? 'our-family' : isChild ? 'child' : 'parent');
  }
}
function submit(dialog, kind) {
  return within(dialog).getByRole('button', { name: kind === 'transfer' ? 'Transfer family contact' : kind === 'close' ? 'Close family permanently' : 'Delete my account permanently' });
}
function deferred() {
  let resolve;
  const promise = new Promise((finish) => { resolve = finish; });
  return { promise, resolve };
}
function responseFinished(method, path) {
  return new Promise((resolve) => {
    const listener = ({ request }) => {
      if (request.method === method && new URL(request.url).pathname === path) {
        server.events.removeListener('response:mocked', listener);
        resolve();
      }
    };
    server.events.on('response:mocked', listener);
  });
}

describe('Account lifecycle', () => {
  it('makes the lifecycle section available from Settings account details', async () => {
    seed();
    renderWithProviders(<SettingsPage />);
    expect(await screen.findByRole('button', { name: 'Delete my account' })).toBeEnabled();
    expect(screen.getByRole('region', { name: 'Account deletion and family handoff' })).toBeInTheDocument();
  });

  it('reviews shared work and truthful retention, and cancellation clears the confirmation without writing', async () => {
    seed();
    const mutation = spyHandler('post', /\/api\/account\/lifecycle\/delete\/$/, new HttpResponse(null, { status: 204 }));
    server.use(mutation.handler);
    const { user } = renderWithProviders(<AccountLifecycle />);
    const dialog = await open(user, 'delete');
    expect(dialog).toHaveTextContent(/private journal never transfers/i);
    expect(dialog).toHaveTextContent(/projects and homework assigned to you.*deleted/i);
    expect(dialog).toHaveTextContent(/backups.*provider copies/i);
    expect(dialog).toHaveTextContent(/files.*retries/i);
    expect(within(dialog).getByLabelText('Shared work to hand off')).toHaveTextContent('Projects2');
    expect(submit(dialog, 'delete')).toBeDisabled();
    await fill(user, dialog, 'delete');
    await user.click(within(dialog).getByRole('button', { name: 'Cancel' }));
    expect(mutation.calls).toHaveLength(0);
    const reopened = await open(user, 'delete');
    expect(within(reopened).getByLabelText('Current password')).toHaveValue('');
    expect(within(reopened).getByLabelText('Type your username to confirm')).toHaveValue('');
    expect(JSON.stringify(localStorage)).not.toContain(PASSWORD);
    expect(JSON.stringify(sessionStorage)).not.toContain(PASSWORD);
  });

  it('transfers the family contact without logging out or claiming extra permissions', async () => {
    let current = preview();
    seed();
    server.use(http.get('*/api/account/lifecycle/', () => HttpResponse.json(current)));
    const mutation = spyHandler('post', /\/api\/account\/lifecycle\/transfer\/$/, () => {
      current = preview({ family: { ...current.family, primary_parent_id: 100 } });
      return new HttpResponse(null, { status: 204 });
    });
    server.use(mutation.handler);
    const { user } = renderWithProviders(<SessionHarness />);
    const dialog = await open(user, 'transfer');
    expect(dialog).toHaveTextContent(/all parents keep equal permissions/i);
    await fill(user, dialog, 'transfer');
    await user.click(submit(dialog, 'transfer'));
    expect(await screen.findByText('Family contact updated. Every parent still has the same access.')).toBeInTheDocument();
    expect(mutation.calls).toHaveLength(1);
    expect(mutation.calls[0]).toMatchObject({ method: 'POST', body: { password: PASSWORD, successor_id: 100 } });
    expect(mutation.calls[0].url).toMatch(/\/api\/account\/lifecycle\/transfer\/$/);
    expect(screen.getByText('Signed in: parent')).toBeInTheDocument();
    expect(localStorage.getItem('abby_auth_token')).toBe('test-session');
  });

  it('deletes a parent only with an explicit successor and signs out the captured account locally', async () => {
    seed();
    const mutation = spyHandler('post', /\/api\/account\/lifecycle\/delete\/$/, new HttpResponse(null, { status: 204 }));
    const logout = spyHandler('post', /\/api\/auth\/$/, {});
    server.use(mutation.handler, logout.handler);
    const { user } = renderWithProviders(<SessionHarness />);
    const dialog = await open(user, 'delete');
    await user.type(within(dialog).getByLabelText('Current password'), PASSWORD);
    await user.type(within(dialog).getByLabelText('Type your username to confirm'), 'parent');
    expect(submit(dialog, 'delete')).toBeDisabled();
    await selectDropdown(user, within(dialog).getByRole('combobox'), 'Other parent');
    await user.click(submit(dialog, 'delete'));
    await waitFor(() => expect(localStorage.getItem('abby_auth_token')).toBeNull());
    expect(mutation.calls[0].body).toEqual({ password: PASSWORD, confirm_username: 'parent', successor_id: 100 });
    expect(mutation.calls[0].url).toMatch(/\/api\/account\/lifecycle\/delete\/$/);
    expect(screen.getByText('Signed out')).toBeInTheDocument();
    expect(logout.calls).toHaveLength(0);
  });

  it('lets a child delete only their own account without a successor or family closure', async () => {
    seed(preview({ user: { id: 7, username: 'child' }, successors: [], can_close_family: false }),
      buildUser({ id: 7, username: 'child', family: actor().family }));
    const mutation = spyHandler('post', /\/api\/account\/lifecycle\/delete\/$/, new HttpResponse(null, { status: 204 }));
    server.use(mutation.handler);
    const { user } = renderWithProviders(<SessionHarness />);
    const dialog = await open(user, 'delete');
    expect(screen.queryByRole('button', { name: 'Close family' })).toBeNull();
    expect(within(dialog).queryByRole('combobox')).toBeNull();
    await fill(user, dialog, 'delete', true);
    await user.click(submit(dialog, 'delete'));
    await waitFor(() => expect(mutation.calls).toHaveLength(1));
    expect(mutation.calls[0].body).toEqual({ password: PASSWORD, confirm_username: 'child' });
    await waitFor(() => expect(localStorage.getItem('abby_auth_token')).toBeNull());
  });

  it('only offers whole-family closure to the last active parent and requires the exact family identifier', async () => {
    seed(preview({ successors: [], can_delete_account: false, can_close_family: true, family_members: { parents: 2, children: 3 } }));
    const mutation = spyHandler('post', /\/api\/account\/lifecycle\/close-family\/$/, new HttpResponse(null, { status: 204 }));
    server.use(mutation.handler);
    const { user } = renderWithProviders(<SessionHarness />);
    expect(await screen.findByRole('button', { name: 'Delete my account' })).toBeDisabled();
    const dialog = await open(user, 'close');
    expect(dialog).toHaveTextContent(/every child and inactive parent/i);
    expect(dialog).toHaveTextContent(/2 parents and 3 children/i);
    expect(dialog).toHaveTextContent(/provider and printer credentials/i);
    await user.type(within(dialog).getByLabelText('Current password'), PASSWORD);
    await user.type(within(dialog).getByLabelText('Type the family identifier to confirm'), 'wrong-family');
    expect(submit(dialog, 'close')).toBeDisabled();
    expect(mutation.calls).toHaveLength(0);
    await user.clear(within(dialog).getByLabelText('Type the family identifier to confirm'));
    await user.type(within(dialog).getByLabelText('Type the family identifier to confirm'), 'our-family');
    await user.click(submit(dialog, 'close'));
    await waitFor(() => expect(localStorage.getItem('abby_auth_token')).toBeNull());
    expect(mutation.calls[0].body).toEqual({ password: PASSWORD, confirm_family_slug: 'our-family', family_version: 'a'.repeat(64) });
    expect(mutation.calls[0].url).toMatch(/\/api\/account\/lifecycle\/close-family\/$/);
  });

  it('disables closure while another active parent exists', async () => {
    seed();
    renderWithProviders(<AccountLifecycle />);
    expect(await screen.findByRole('button', { name: 'Close family' })).toBeDisabled();
    expect(screen.getByText(/Only the last active parent can close/i)).toBeInTheDocument();
  });

  it.each(['transfer', 'close'])('cancels %s without sending a mutation or persisting credentials', async (kind) => {
    seed(kind === 'close' ? preview({ successors: [], can_delete_account: false, can_close_family: true }) : preview());
    const mutation = spyHandler('post', /\/api\/account\/lifecycle\/(?:transfer|close-family)\/$/, new HttpResponse(null, { status: 204 }));
    server.use(mutation.handler);
    const { user } = renderWithProviders(<AccountLifecycle />);
    const dialog = await open(user, kind);
    await fill(user, dialog, kind);
    await user.click(within(dialog).getByRole('button', { name: 'Cancel' }));
    expect(mutation.calls).toHaveLength(0);
    expect(screen.queryByRole('dialog')).toBeNull();
    expect(JSON.stringify(localStorage)).not.toContain(PASSWORD);
    expect(JSON.stringify(sessionStorage)).not.toContain(PASSWORD);
  });

  it('keeps current-password validation beside its field and preserves the form for correction', async () => {
    seed();
    const mutation = spyHandler('post', /\/api\/account\/lifecycle\/delete\/$/,
      HttpResponse.json({ password: ['Enter your current Abby password.'] }, { status: 400 }));
    server.use(mutation.handler);
    const { user } = renderWithProviders(<AccountLifecycle />);
    const dialog = await open(user, 'delete');
    expect(dialog).toHaveTextContent(/ask a family parent or operator for a password reset/i);
    await fill(user, dialog, 'delete');
    await user.click(submit(dialog, 'delete'));
    expect(await within(dialog).findByRole('alert')).toHaveTextContent('Enter your current Abby password.');
    expect(within(dialog).getByLabelText('Current password')).toHaveAttribute('aria-invalid', 'true');
    expect(within(dialog).getByLabelText('Current password')).toHaveValue(PASSWORD);
    expect(dialog).not.toHaveTextContent('{"password"');
    expect(mutation.calls).toHaveLength(1);
    expect(mutation.calls[0].body).toMatchObject({ password: PASSWORD, confirm_username: 'parent', successor_id: 100 });
  });

  it('requires a fresh impact review after the family changed instead of retrying a stale closure', async () => {
    let current = preview({ successors: [], can_delete_account: false, can_close_family: true });
    seed(current);
    server.use(http.get('*/api/account/lifecycle/', () => HttpResponse.json(current)));
    const mutation = spyHandler('post', /\/api\/account\/lifecycle\/close-family\/$/, () => {
      current = { ...current, family_members: { parents: 2, children: 4 }, family_version: 'b'.repeat(64) };
      return HttpResponse.json({ detail: 'Family changed. Review it again.' }, { status: 409 });
    });
    server.use(mutation.handler);
    const { user } = renderWithProviders(<AccountLifecycle />);
    const dialog = await open(user, 'close');
    await fill(user, dialog, 'close');
    await user.click(submit(dialog, 'close'));
    expect(await within(dialog).findByRole('alert')).toHaveTextContent('Family changed. Review it again.');
    expect(submit(dialog, 'close')).toBeDisabled();
    expect(mutation.calls).toHaveLength(1);
    expect(mutation.calls[0].body.family_version).toBe('a'.repeat(64));
    await user.click(within(dialog).getByRole('button', { name: 'Review updated family' }));
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    const next = await open(user, 'close');
    expect(next).toHaveTextContent('2 parents and 4 children');
    expect(within(next).getByLabelText('Current password')).toHaveValue('');
    expect(within(next).getByLabelText('Type the family identifier to confirm')).toHaveValue('');
    expect(submit(next, 'close')).toBeDisabled();
    expect(mutation.calls).toHaveLength(1);
  });

  it.each(['transfer', 'delete', 'close'])('retains the %s form after failure and blocks duplicate submissions and dismissal during retry', async (kind) => {
    seed(kind === 'close' ? preview({ successors: [], can_delete_account: false, can_close_family: true }) : preview());
    let attempts = 0;
    const pending = deferred();
    const path = `/api/account/lifecycle/${kind === 'close' ? 'close-family' : kind}/`;
    const mutation = spyHandler('post', new RegExp(`${path}$`), async () => {
      if (++attempts === 1) return HttpResponse.json({ error: 'Temporary failure.' }, { status: 503 });
      await pending.promise;
      return new HttpResponse(null, { status: 204 });
    });
    server.use(mutation.handler);
    const { user } = renderWithProviders(<SessionHarness />);
    const dialog = await open(user, kind);
    await fill(user, dialog, kind);
    await user.click(submit(dialog, kind));
    expect(await within(dialog).findByRole('alert')).toHaveTextContent(/Could not confirm this change/i);
    expect(within(dialog).getByLabelText('Current password')).toHaveValue(PASSWORD);
    try {
      await user.dblClick(submit(dialog, kind));
      await waitFor(() => expect(mutation.calls).toHaveLength(2));
      expect(within(dialog).getByRole('button', { name: 'Confirming…' })).toBeDisabled();
      expect(within(dialog).getByRole('button', { name: 'Cancel' })).toBeDisabled();
      await user.keyboard('{Escape}');
      expect(dialog).toBeInTheDocument();
      expect(mutation.calls[1].body).toEqual(mutation.calls[0].body);
    } finally {
      const completed = responseFinished('POST', path);
      await act(async () => { pending.resolve(); await completed; });
    }
  });

  it.each(['transfer', 'delete', 'close'].flatMap((kind) => [204, 400, 401].map((status) => [kind, status])))('ignores a delayed %s response after an account replacement (%s)', async (kind, status) => {
    seed(kind === 'close' ? preview({ successors: [], can_delete_account: false, can_close_family: true }) : preview());
    const pending = deferred();
    const path = `/api/account/lifecycle/${kind === 'close' ? 'close-family' : kind}/`;
    const mutation = spyHandler('post', new RegExp(`${path}$`), async () => {
      await pending.promise;
      return status === 204 ? new HttpResponse(null, { status }) : HttpResponse.json({ error: 'Old account failure.' }, { status });
    });
    server.use(mutation.handler);
    const { user } = renderWithProviders(<SessionHarness />);
    const dialog = await open(user, kind);
    await fill(user, dialog, kind);
    await user.click(submit(dialog, kind));
    await waitFor(() => expect(mutation.calls).toHaveLength(1));
    server.use(http.get('*/api/account/lifecycle/', () => HttpResponse.json(preview({ user: { id: 200, username: 'replacement' }, family: { id: 2, name: 'New family', slug: 'new-family', primary_parent_id: 200 } }))));
    await user.click(screen.getByRole('button', { name: 'Switch account' }));
    await screen.findByRole('button', { name: 'Delete my account' });
    const completed = responseFinished('POST', path);
    await act(async () => { pending.resolve(); await completed; });
    expect(localStorage.getItem('abby_auth_token')).toBe('replacement-session');
    expect(screen.getByText('Signed in: replacement')).toBeInTheDocument();
    expect(screen.queryByText('Old account failure.')).toBeNull();
    expect(screen.queryByLabelText('Current password')).toBeNull();
  });

  it('ignores an older family preview after switching accounts while the read is pending', async () => {
    seed();
    const pending = deferred();
    let oldStarted = false;
    server.use(http.get('*/api/account/lifecycle/', async ({ request }) => {
      if (request.headers.get('Authorization') === 'Token test-session') {
        oldStarted = true;
        await pending.promise;
        return HttpResponse.json(preview());
      }
      return HttpResponse.json(preview({ user: { id: 200, username: 'replacement' }, family: { id: 2, name: 'New family', slug: 'new-family', primary_parent_id: 200 }, successors: [] }));
    }));
    const { user } = renderWithProviders(<SessionHarness />);
    await waitFor(() => expect(oldStarted).toBe(true));
    await user.click(screen.getByRole('button', { name: 'Switch account' }));
    await screen.findByRole('button', { name: 'Delete my account' });
    const completed = responseFinished('GET', '/api/account/lifecycle/');
    await act(async () => { pending.resolve(); await completed; });
    expect(screen.queryByRole('button', { name: 'Transfer family contact' })).toBeNull();
    expect(screen.getByText('Signed in: replacement')).toBeInTheDocument();
  });

  it('holds actions on failed or mismatched previews and supports a fresh read', async () => {
    seed(preview({ family: { id: 22, name: 'Wrong family', slug: 'wrong-family' } }));
    const { user } = renderWithProviders(<AccountLifecycle />);
    expect(await screen.findByRole('alert')).toHaveTextContent(/Could not load/i);
    expect(screen.queryByRole('button', { name: 'Delete my account' })).toBeNull();
    server.use(http.get('*/api/account/lifecycle/', () => HttpResponse.json(preview())));
    await user.click(screen.getByRole('button', { name: 'Retry account options' }));
    expect(await screen.findByRole('button', { name: 'Delete my account' })).toBeEnabled();
  });

  it('keeps a pending confirmation through a same-account profile update', async () => {
    seed();
    const pending = deferred();
    const mutation = spyHandler('post', /\/api\/account\/lifecycle\/delete\/$/, async () => {
      await pending.promise;
      return new HttpResponse(null, { status: 204 });
    });
    server.use(mutation.handler);
    const { user } = renderWithProviders(<SessionHarness />);
    const dialog = await open(user, 'delete');
    await fill(user, dialog, 'delete');
    await user.click(submit(dialog, 'delete'));
    await waitFor(() => expect(mutation.calls).toHaveLength(1));
    try {
      await user.click(screen.getByRole('button', { name: 'Update current profile' }));
      expect(dialog).toBeInTheDocument();
      expect(within(dialog).getByRole('button', { name: 'Confirming…' })).toBeDisabled();
    } finally {
      const completed = responseFinished('POST', '/api/account/lifecycle/delete/');
      await act(async () => { pending.resolve(); await completed; });
    }
    await waitFor(() => expect(localStorage.getItem('abby_auth_token')).toBeNull());
    expect(mutation.calls).toHaveLength(1);
  });
});
