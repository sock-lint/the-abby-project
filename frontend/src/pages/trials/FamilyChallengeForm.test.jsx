import { describe, expect, it, vi } from 'vitest';
import { useEffect, useState } from 'react';
import { http, HttpResponse } from 'msw';
import { renderWithProviders, screen, within, waitFor, act } from '../../test/render';
import { server } from '../../test/server';
import { spyHandler } from '../../test/spy';
import { buildParent, buildUser } from '../../test/factories';
import { selectDropdown } from '../../test/selectDropdown';
import FamilyChallengeForm from './FamilyChallengeForm';
import { useRole } from '../../hooks/useRole';

const CHILDREN = [{ id: 7, display_name: 'Abby' }, { id: 8, display_name: 'Beck' }, { id: 9, display_name: 'Charlie' }];
const DEFINITION = { id: 31, name: 'Family workshop', description: 'Build together.', is_cooperative: true, catalog_available: true, quest_type: 'collection', target_value: 5, duration_days: 7, coin_reward: 20, xp_reward: 40, reward_items: [{ id: 5, item_name: 'Birdseed', quantity: 2 }] };

function AuthState() {
  const { user } = useRole();
  return user && <span>Authenticated test session</span>;
}

function setup({ role = 'parent', children = CHILDREN, catalog = [DEFINITION], onAssigned = vi.fn() } = {}) {
  const reads = spyHandler('get', /\/api\/quests\/catalog\/$/, catalog);
  server.use(http.get('*/api/auth/me/', () => HttpResponse.json(role === 'parent' ? buildParent() : buildUser())), reads.handler);
  return { ...renderWithProviders(<><FamilyChallengeForm children={children} onAssigned={onAssigned} /><AuthState /></>), reads, onAssigned };
}

async function openForm(user) {
  await user.click(await screen.findByRole('button', { name: 'Family challenges' }));
  const dialog = screen.getByRole('dialog', { name: 'Assign a family challenge' });
  await waitFor(() => expect(within(dialog).getByRole('combobox', { name: 'Family challenge' })).toBeEnabled());
  await selectDropdown(user, within(dialog).getByRole('combobox', { name: 'Family challenge' }), '31');
  return dialog;
}

describe('Parent family challenge assignment', () => {
  it.each(['child', 'parent'])('does not load the catalog without a parent and at least two children (%s)', async (role) => {
    const { reads } = setup({ role, children: role === 'parent' ? CHILDREN.slice(0, 1) : CHILDREN });
    // Auth is resolved before checking that no catalog request was made.
    await screen.findByText('Authenticated test session');
    expect(screen.queryByRole('button', { name: 'Family challenges' })).not.toBeInTheDocument();
    expect(reads.calls).toHaveLength(0);
  });

  it('offers only available shared definitions and requires two explicit participants', async () => {
    const assign = spyHandler('post', /\/api\/quests\/31\/co-op\/$/, { id: 51 });
    server.use(assign.handler);
    const { user, onAssigned } = setup({ catalog: [DEFINITION, { ...DEFINITION, id: 32, name: 'Personal challenge', is_cooperative: false }, { ...DEFINITION, id: 33, name: 'Unavailable family challenge', catalog_available: false }] });
    await user.click(await screen.findByRole('button', { name: 'Family challenges' }));
    const dialog = screen.getByRole('dialog');
    await waitFor(() => expect(within(dialog).getByRole('combobox', { name: 'Family challenge' })).toBeEnabled());
    await user.click(within(dialog).getByRole('combobox', { name: 'Family challenge' }));
    expect(screen.queryByRole('option', { name: 'Personal challenge' })).not.toBeInTheDocument();
    expect(screen.queryByRole('option', { name: 'Unavailable family challenge' })).not.toBeInTheDocument();
    await user.click(screen.getByRole('option', { name: 'Family workshop' }));
    expect(within(dialog).getByText('Work together toward one shared target. Each selected child receives the full completion reward.')).toBeInTheDocument();
    expect(within(dialog).getByText('Shared target: 5 activities · 7 days')).toBeInTheDocument();
    expect(within(dialog).getByText('Completion reward for each child: 20 coins · 40 XP')).toBeInTheDocument();
    expect(within(dialog).getByText('Birdseed ×2')).toBeInTheDocument();
    const submit = within(dialog).getByRole('button', { name: 'Assign family challenge' });
    expect(submit).toBeDisabled();
    await user.click(within(dialog).getByRole('checkbox', { name: 'Abby' }));
    expect(submit).toBeDisabled();
    expect(assign.calls).toHaveLength(0);
    await user.click(within(dialog).getByRole('checkbox', { name: 'Beck' }));
    await user.click(submit);
    await waitFor(() => expect(assign.calls).toHaveLength(1));
    expect(assign.calls[0].url).toMatch(/\/api\/quests\/31\/co-op\/$/);
    expect(assign.calls[0].body).toEqual({ user_ids: [7, 8] });
    await waitFor(() => expect(onAssigned).toHaveBeenCalledOnce());
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('retains the selected challenge and participants after rejection and retries only on explicit submit', async () => {
    const assign = spyHandler('post', /\/api\/quests\/31\/co-op\/$/, () => HttpResponse.json({ error: 'An existing personal reward promise must finish first.' }, { status: 400 }));
    server.use(assign.handler);
    const { user, onAssigned } = setup();
    const dialog = await openForm(user);
    await user.click(within(dialog).getByRole('checkbox', { name: 'Abby' }));
    await user.click(within(dialog).getByRole('checkbox', { name: 'Beck' }));
    await user.click(within(dialog).getByRole('button', { name: 'Assign family challenge' }));
    expect(await within(dialog).findByRole('alert')).toHaveTextContent('An existing personal reward promise must finish first.');
    expect(within(dialog).getByRole('combobox', { name: 'Family challenge' })).toHaveValue('31');
    expect(within(dialog).getByRole('checkbox', { name: 'Abby' })).toBeChecked();
    expect(within(dialog).getByRole('checkbox', { name: 'Beck' })).toBeChecked();
    expect(assign.calls).toHaveLength(1);
    expect(onAssigned).not.toHaveBeenCalled();
    const retry = spyHandler('post', /\/api\/quests\/31\/co-op\/$/, { id: 51 });
    server.use(retry.handler);
    await user.click(within(dialog).getByRole('button', { name: 'Assign family challenge' }));
    await waitFor(() => expect(retry.calls).toHaveLength(1));
    expect(retry.calls[0].body).toEqual({ user_ids: [7, 8] });
    await waitFor(() => expect(onAssigned).toHaveBeenCalledOnce());
  });

  it('recovers a failed catalog read through an explicit retry', async () => {
    const { user, reads } = setup({ catalog: () => HttpResponse.json({ error: 'Family challenges are unavailable.' }, { status: 503 }) });
    await user.click(await screen.findByRole('button', { name: 'Family challenges' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Family challenges are unavailable.');
    expect(reads.calls).toHaveLength(1);
    expect(screen.getByRole('button', { name: 'Assign family challenge' })).toBeDisabled();
    const retry = spyHandler('get', /\/api\/quests\/catalog\/$/, [DEFINITION]);
    server.use(retry.handler);
    await user.click(screen.getByRole('button', { name: 'Retry family challenges' }));
    await waitFor(() => expect(retry.calls).toHaveLength(1));
    await waitFor(() => expect(screen.getByRole('combobox', { name: 'Family challenge' })).toBeEnabled());
    await selectDropdown(user, screen.getByRole('combobox', { name: 'Family challenge' }), '31');
    expect(screen.getByRole('region', { name: 'Family challenge preview' })).toHaveTextContent('Build together.');
  });

  it('ignores a delayed assignment response after its credential changes', async () => {
    let finish;
    const assign = spyHandler('post', /\/api\/quests\/31\/co-op\/$/, () => new Promise((resolve) => { finish = () => resolve({ id: 51 }); }));
    server.use(assign.handler);
    const { user, onAssigned } = setup();
    const dialog = await openForm(user);
    await user.click(within(dialog).getByRole('checkbox', { name: 'Abby' }));
    await user.click(within(dialog).getByRole('checkbox', { name: 'Beck' }));
    await user.click(within(dialog).getByRole('button', { name: 'Assign family challenge' }));
    await waitFor(() => expect(assign.calls).toHaveLength(1));
    localStorage.setItem('abby_auth_token', 'replacement-session');
    await act(async () => finish());
    expect(onAssigned).not.toHaveBeenCalled();
  });

  it('discards selections when the verified family roster changes', async () => {
    let changeRoster;
    function ChangingRoster() {
      const [children, setChildren] = useState(CHILDREN);
      useEffect(() => { changeRoster = setChildren; }, []);
      return <FamilyChallengeForm children={children} />;
    }
    server.use(
      http.get('*/api/auth/me/', () => HttpResponse.json(buildParent())),
      http.get('*/api/quests/catalog/', () => HttpResponse.json([DEFINITION])),
    );
    const { user } = renderWithProviders(<ChangingRoster />);
    const dialog = await openForm(user);
    await user.click(within(dialog).getByRole('checkbox', { name: 'Abby' }));
    await user.click(within(dialog).getByRole('checkbox', { name: 'Beck' }));
    act(() => changeRoster([CHILDREN[0], CHILDREN[2]]));
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Family challenges' }));
    expect(screen.getByRole('combobox', { name: 'Family challenge' })).toHaveValue('');
    expect(screen.getByRole('checkbox', { name: 'Abby' })).not.toBeChecked();
    expect(screen.queryByRole('checkbox', { name: 'Beck' })).not.toBeInTheDocument();
    expect(screen.getByRole('checkbox', { name: 'Charlie' })).not.toBeChecked();
  });
});
