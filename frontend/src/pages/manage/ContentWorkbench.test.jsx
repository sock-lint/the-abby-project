import { describe, expect, it, vi } from 'vitest';
import { act, fireEvent, screen, waitFor, within } from '@testing-library/react';
import { http, HttpResponse } from 'msw';
import ContentWorkbench from './ContentWorkbench';
import { renderWithProviders } from '../../test/render';
import { buildParent, buildUser } from '../../test/factories';
import { server } from '../../test/server';
import { spyHandler } from '../../test/spy';
import { selectDropdown } from '../../test/selectDropdown';
import { useAuth } from '../../hooks/useApi';

import { draftId, itemValues, config, draft, change, saved, previewed, metadata, comparison } from '../../test/contentWorkbenchFixtures';

function setup(data = metadata, currentDraft = draft) {
  server.use(
    http.get('*/api/auth/me/', () => HttpResponse.json(buildParent())),
    http.get('*/api/rpg/content-workbench/', () => HttpResponse.json(data)),
    http.get(`*/api/rpg/content-workbench/drafts/${draftId}/`, () => HttpResponse.json(currentDraft)),
  );
}
async function openDraft(user) {
  await selectDropdown(user, await screen.findByRole('combobox', { name: 'Open draft' }), draftId);
  await screen.findByText('Saved draft loaded.');
}
async function openChallenge(user) {
  await user.click(screen.getByRole('button', { name: /🌲 Forest reading/ }));
  return screen.getByRole('form', { name: 'Challenge editor' });
}

describe('RPG content workbench', () => {
  it('uses server permission checks and does not expose catalog or controls to regular parents', async () => {
    setup();
    server.use(http.get('*/api/rpg/content-workbench/', () => HttpResponse.json({ detail: 'Staff parents only.' }, { status: 403 })));
    renderWithProviders(<ContentWorkbench />);
    await screen.findByText('RPG content management is available to staff parents.');
    expect(screen.queryByRole('button', { name: 'Create draft' })).toBeNull();
    expect(screen.queryByText('Forest reading')).toBeNull();
  });

  it('never requests designer data for a child', async () => {
    const calls = vi.fn();
    server.use(http.get('*/api/auth/me/', () => HttpResponse.json(buildUser())), http.get('*/api/rpg/content-workbench/', () => { calls(); return HttpResponse.json(metadata); }));
    renderWithProviders(<ContentWorkbench />);
    await screen.findByText('RPG content management is available to staff parents.');
    expect(calls).not.toHaveBeenCalled();
  });

  it('retries a failed metadata read and does not present the error as an empty catalog', async () => {
    setup();
    server.use(http.get('*/api/rpg/content-workbench/', () => HttpResponse.json({ detail: 'Catalog unavailable.' }, { status: 503 })));
    const { user } = renderWithProviders(<ContentWorkbench />);
    await screen.findByRole('alert');
    expect(screen.queryByText(/No challenges match/)).toBeNull();
    setup();
    await user.click(screen.getByRole('button', { name: 'Try again' }));
    await screen.findByRole('button', { name: /🌲 Forest reading/ });
  });

  it('creates a durable named draft without changing published content', async () => {
    setup();
    const create = spyHandler('post', /\/api\/rpg\/content-workbench\/drafts\/$/, draft);
    server.use(create.handler);
    const { user } = renderWithProviders(<ContentWorkbench />);
    await user.type(await screen.findByRole('textbox', { name: 'New draft name' }), 'Forest balance');
    await user.click(screen.getByRole('button', { name: 'Create draft' }));
    await screen.findByText(/Draft created/);
    expect(create.calls).toHaveLength(1);
    expect(create.calls[0]).toMatchObject({ url: expect.stringMatching(/\/api\/rpg\/content-workbench\/drafts\/$/), body: { name: 'Forest balance' } });
    expect(screen.queryByRole('button', { name: 'Publish reviewed draft' })).toBeNull();
  });

  it('shows item availability, published connections and links to the owning challenge', async () => {
    setup();
    const { user } = renderWithProviders(<ContentWorkbench />);
    await user.click(await screen.findByRole('button', { name: 'Items', exact: true }));
    await user.click(screen.getByRole('button', { name: /🍓 Forest snack/ }));
    const uses = screen.getByRole('region', { name: 'Item connections' });
    expect(within(uses).getByText(/Available for new acquisition/)).toBeVisible();
    expect(within(uses).getByText(/Drop: reading logged/)).toBeVisible();
    expect(within(uses).getByText(/Shop: Snack offer · 12 coins/)).toBeVisible();
    expect(screen.getByRole('textbox', { name: 'Name' })).toBeDisabled();
    await user.click(within(uses).getByRole('button', { name: 'Forest reading · 1 awarded' }));
    expect(screen.getByRole('form', { name: 'Challenge editor' })).toBeInTheDocument();
  });

  it('saves the edited challenge, rewards and XP skill tags to the exact optimistic draft revision', async () => {
    setup();
    const patch = spyHandler('patch', new RegExp(`/api/rpg/content-workbench/drafts/${draftId}/$`), ({ body }) => ({ ...saved, changes: body.changes }));
    server.use(patch.handler);
    const { user } = renderWithProviders(<ContentWorkbench />);
    await openDraft(user);
    await openChallenge(user);
    fireEvent.change(screen.getByRole('spinbutton', { name: 'Coin reward' }), { target: { value: '25' } });
    fireEvent.change(screen.getByRole('spinbutton', { name: 'Quantity 1' }), { target: { value: '2' } });
    await user.click(screen.getByRole('checkbox', { name: 'chore complete' }));
    await user.click(screen.getByRole('button', { name: 'Save to draft' }));
    await screen.findByText(/Changes saved to draft/);
    expect(patch.calls).toHaveLength(1);
    expect(patch.calls[0].url).toMatch(new RegExp(`/api/rpg/content-workbench/drafts/${draftId}/$`));
    expect(patch.calls[0].body).toEqual({ revision: 1, changes: [{ ...change, values: { ...change.values, reward_items: [{ item_id: 7, quantity: 2 }], trigger_filter: { allowed_triggers: ['reading_logged', 'chore_complete'] } } }] });
    expect(screen.getByRole('button', { name: 'Preview changes and audit rewards' })).toBeEnabled();
  });

  it.each([true, false])('saves and previews shared family challenge mode as %s', async (is_cooperative) => {
    const before = { ...metadata.catalog.quests[0].values, is_cooperative: !is_cooperative };
    setup({ ...metadata, catalog: { ...metadata.catalog, quests: [{ ...metadata.catalog.quests[0], is_cooperative: !is_cooperative, values: before }] } });
    let savedChanges;
    const patch = spyHandler('patch', new RegExp(`/api/rpg/content-workbench/drafts/${draftId}/$`), ({ body }) => {
      savedChanges = body.changes;
      return { ...saved, changes: savedChanges };
    });
    const preview = spyHandler('post', new RegExp(`/api/rpg/content-workbench/drafts/${draftId}/preview/$`), () => ({
      ...saved, changes: savedChanges, preview: { ...previewed.preview, changes: [{ object: 'quests:9', action: 'update', before, after: savedChanges[0].values }] },
    }));
    server.use(patch.handler, preview.handler);
    const { user } = renderWithProviders(<ContentWorkbench />);
    await openDraft(user);
    await openChallenge(user);
    const mode = screen.getByRole('checkbox', { name: 'Shared family challenge' });
    expect(mode.checked).toBe(!is_cooperative);
    expect(mode).toHaveAccessibleDescription('A parent selects at least two children to work toward one shared target. Each participant receives the full completion reward.');
    await user.click(mode);
    await user.click(screen.getByRole('button', { name: 'Save to draft' }));
    await screen.findByText(/Changes saved to draft/);
    expect(patch.calls).toHaveLength(1);
    expect(patch.calls[0]).toMatchObject({ url: expect.stringMatching(new RegExp(`/api/rpg/content-workbench/drafts/${draftId}/$`)), body: { revision: 1, changes: [{ ...change, values: { ...before, is_cooperative } }] } });
    await user.click(screen.getByRole('button', { name: 'Close editor' }));
    await openChallenge(user);
    expect(screen.getByRole('checkbox', { name: 'Shared family challenge' }).checked).toBe(is_cooperative);
    await user.click(screen.getByRole('button', { name: 'Preview changes and audit rewards' }));
    const exactPreview = await screen.findByRole('region', { name: 'Exact publication preview' });
    expect(preview.calls).toHaveLength(1);
    expect(preview.calls[0]).toMatchObject({ url: expect.stringMatching(/\/preview\/$/), body: { revision: 2 } });
    await user.click(within(exactPreview).getByText('update: Forest reading'));
    expect(within(exactPreview).getByText('is cooperative')).toBeVisible();
    expect(within(exactPreview).getByText(`Before: ${!is_cooperative}`)).toBeVisible();
    expect(within(exactPreview).getByText(`After: ${is_cooperative}`)).toBeVisible();
  });

  it('lets an author remove legacy activity filters without offering them for new challenges', async () => {
    setup({ ...metadata, rules: { ...metadata.rules, triggers: ['chore_complete'] } });
    const patch = spyHandler('patch', new RegExp(`/api/rpg/content-workbench/drafts/${draftId}/$`), ({ body }) => ({ ...saved, changes: body.changes }));
    server.use(patch.handler);
    const { user } = renderWithProviders(<ContentWorkbench />);
    await openDraft(user); await openChallenge(user);
    const retained = screen.getByRole('checkbox', { name: 'reading logged · not tracked by current challenges' });
    expect(retained).toBeChecked();
    await user.click(retained);
    await user.click(screen.getByRole('checkbox', { name: 'chore complete' }));
    await user.click(screen.getByRole('button', { name: 'Save to draft' }));
    await screen.findByText(/Changes saved to draft/);
    expect(patch.calls).toHaveLength(1);
    expect(patch.calls[0].body).toEqual({ revision: 1, changes: [{ ...change, values: { ...metadata.catalog.quests[0].values, trigger_filter: { allowed_triggers: ['chore_complete'] } } }] });
    await user.click(screen.getByRole('button', { name: 'New challenge', exact: true }));
    expect(screen.queryByRole('checkbox', { name: /reading logged/ })).toBeNull();
    expect(screen.getByRole('checkbox', { name: 'chore complete' })).not.toBeChecked();
  });

  it('limits boss activities to the server damage-producing choices and exposes a retained incompatible filter', async () => {
    const quest = metadata.catalog.quests[0];
    const trigger_filter = { allowed_triggers: ['creation_logged'] };
    setup({ ...metadata, rules: { ...metadata.rules, triggers: ['chore_complete', 'creation_logged'], boss_triggers: ['chore_complete'] }, catalog: { ...metadata.catalog, quests: [{ ...quest, trigger_filter, values: { ...quest.values, trigger_filter } }] } });
    const { user } = renderWithProviders(<ContentWorkbench />);
    await openDraft(user); await openChallenge(user);
    expect(screen.getByRole('checkbox', { name: 'creation logged' })).toBeChecked();
    await selectDropdown(user, screen.getByRole('combobox', { name: 'Challenge type' }), 'boss');
    await user.click(screen.getByRole('checkbox', { name: 'creation logged · not tracked by current challenges' }));
    expect(screen.queryByRole('checkbox', { name: /creation logged/ })).toBeNull();
    expect(screen.getByRole('checkbox', { name: 'chore complete' })).not.toBeChecked();
  });

  it('creates an item in the draft and keeps its type-specific properties outside the main editing flow', async () => {
    setup();
    const patch = spyHandler('patch', new RegExp(`/api/rpg/content-workbench/drafts/${draftId}/$`), ({ body }) => ({ ...saved, changes: body.changes }));
    server.use(patch.handler);
    const { user } = renderWithProviders(<ContentWorkbench />);
    await openDraft(user);
    await user.click(screen.getByRole('button', { name: 'Items', exact: true }));
    await user.click(screen.getByRole('button', { name: 'New item', exact: true }));
    await user.type(screen.getByRole('textbox', { name: 'Name', exact: true }), 'Trail snack');
    await user.type(screen.getByRole('textbox', { name: 'Stable item key' }), 'trail-snack');
    await user.click(screen.getByText('Advanced item properties'));
    fireEvent.change(screen.getByRole('textbox', { name: 'Item properties (JSON)' }), { target: { value: '{"growth":8}' } });
    await user.click(screen.getByRole('button', { name: 'Save to draft' }));
    await screen.findByText(/Changes saved to draft/);
    expect(patch.calls).toHaveLength(1);
    expect(patch.calls[0].body).toMatchObject({ revision: 1, changes: [{ section: 'items', object_id: null, key: expect.any(String), values: { name: 'Trail snack', slug: 'trail-snack', item_type: 'food', metadata: { growth: 8 } } }] });
  });

  it('connects a new challenge to an item in the same durable draft using its stable draft key', async () => {
    const newItem = { section: 'items', key: 'new-snack', object_id: null, values: { ...itemValues, name: 'New snack', slug: 'new-snack', item_type: 'food' } };
    setup(metadata, { ...draft, changes: [newItem] });
    const patch = spyHandler('patch', new RegExp(`/api/rpg/content-workbench/drafts/${draftId}/$`), ({ body }) => ({ ...saved, changes: body.changes }));
    server.use(patch.handler);
    const { user } = renderWithProviders(<ContentWorkbench />);
    await openDraft(user);
    await user.click(screen.getByRole('button', { name: 'New challenge', exact: true }));
    expect(screen.getByRole('checkbox', { name: 'Shared family challenge' })).not.toBeChecked();
    await user.type(screen.getByRole('textbox', { name: 'Name', exact: true }), 'Trail days');
    await user.type(screen.getByRole('textbox', { name: 'Description' }), 'Complete five activities.');
    await user.type(screen.getByRole('searchbox', { name: 'Search reward items' }), 'New snack');
    await user.click(screen.getByRole('button', { name: 'Add reward item' }));
    await user.click(screen.getByRole('button', { name: 'Add skill' }));
    await user.click(screen.getByRole('button', { name: 'Save to draft' }));
    await screen.findByText(/Changes saved to draft/);
    expect(patch.calls[0].body.changes[0]).toEqual(newItem);
    expect(patch.calls[0].body.changes[1]).toMatchObject({ section: 'quests', object_id: null, key: expect.any(String), values: { name: 'Trail days', is_cooperative: false, reward_items: [{ item_key: 'new-snack', quantity: 1 }], skill_tags: [{ skill_id: 4, xp_weight: 1 }] } });
    expect(patch.calls[0].body.changes[1].values).not.toHaveProperty('is_system');
  });

  it('keeps invalid advanced properties in the editor without sending them to the server', async () => {
    setup();
    const patch = spyHandler('patch', new RegExp(`/api/rpg/content-workbench/drafts/${draftId}/$`), saved);
    server.use(patch.handler);
    const { user } = renderWithProviders(<ContentWorkbench />);
    await openDraft(user);
    await user.click(screen.getByRole('button', { name: 'Items', exact: true }));
    await user.click(screen.getByRole('button', { name: 'New item', exact: true }));
    await user.type(screen.getByRole('textbox', { name: 'Name', exact: true }), 'Trail snack');
    await user.type(screen.getByRole('textbox', { name: 'Stable item key' }), 'trail-snack');
    await user.click(screen.getByText('Advanced item properties'));
    fireEvent.change(screen.getByRole('textbox', { name: 'Item properties (JSON)' }), { target: { value: '{"growth":' } });
    await user.click(screen.getByRole('button', { name: 'Save to draft' }));
    expect(screen.getByRole('alert')).toHaveTextContent('Item properties must be a valid JSON object.');
    expect(screen.getByRole('textbox', { name: 'Item properties (JSON)' })).toHaveValue('{"growth":');
    expect(patch.calls).toHaveLength(0);
  });

  it('preserves behavior on existing items and creates an editable new version for future rewards', async () => {
    setup();
    const patch = spyHandler('patch', new RegExp(`/api/rpg/content-workbench/drafts/${draftId}/$`), ({ body }) => ({ ...saved, changes: body.changes }));
    server.use(patch.handler);
    const { user } = renderWithProviders(<ContentWorkbench />);
    await openDraft(user);
    await user.click(screen.getByRole('button', { name: 'Items', exact: true }));
    await user.click(screen.getByRole('button', { name: /🍓 Forest snack/ }));
    expect(screen.getByRole('combobox', { name: 'Rarity' })).toBeDisabled();
    expect(screen.getByRole('spinbutton', { name: 'Coin value' })).toBeDisabled();
    expect(screen.getByText(/items already owned or promised/)).toBeVisible();
    await user.click(screen.getByRole('button', { name: 'Create new item version' }));
    expect(screen.getByRole('textbox', { name: 'Stable item key' })).toHaveValue('forest-snack-v2');
    expect(screen.getByRole('textbox', { name: 'Name', exact: true })).toHaveValue('Forest snack v2');
    fireEvent.change(screen.getByRole('spinbutton', { name: 'Coin value' }), { target: { value: '6' } });
    await selectDropdown(user, screen.getByRole('combobox', { name: 'Rarity' }), 'rare');
    await user.click(screen.getByRole('button', { name: 'Save to draft' }));
    await screen.findByText(/Changes saved to draft/);
    expect(patch.calls[0].body).toMatchObject({ revision: 1, changes: [{ section: 'items', object_id: null, values: { slug: 'forest-snack-v2', item_type: 'food', name: 'Forest snack v2', coin_value: 6, rarity: 'rare', metadata: { growth: 5 } } }] });
    expect(patch.calls[0].body.changes[0].key).not.toBe('items-7');
  });

  it('keeps unsaved editor changes after a save failure and protects them when selecting another entry', async () => {
    setup();
    const patch = spyHandler('patch', new RegExp(`/api/rpg/content-workbench/drafts/${draftId}/$`), HttpResponse.json({ detail: 'Draft changed in another tab.' }, { status: 409 }));
    server.use(patch.handler);
    const { user } = renderWithProviders(<ContentWorkbench />);
    await openDraft(user); await openChallenge(user);
    fireEvent.change(screen.getByRole('spinbutton', { name: 'Coin reward' }), { target: { value: '25' } });
    await user.click(screen.getByRole('button', { name: 'Save to draft' }));
    await screen.findByText(/Your inputs have been kept/);
    expect(screen.getByRole('spinbutton', { name: 'Coin reward' })).toHaveValue(25);
    await user.click(screen.getByRole('button', { name: 'Items', exact: true }));
    await user.click(screen.getByRole('button', { name: /🍓 Forest snack/ }));
    const dialog = screen.getByRole('alertdialog', { name: 'Discard unsaved editor changes?' });
    await user.click(within(dialog).getByRole('button', { name: 'Cancel' }));
    expect(screen.getByRole('spinbutton', { name: 'Coin reward' })).toHaveValue(25);
    expect(patch.calls).toHaveLength(1);
  });

  it('previews and audits the saved draft, compares it, then publishes only after explicit confirmation', async () => {
    setup(metadata, saved);
    const preview = spyHandler('post', new RegExp(`/drafts/${draftId}/preview/$`), previewed);
    const simulation = spyHandler('post', new RegExp(`/drafts/${draftId}/simulate/$`), comparison);
    const publish = spyHandler('post', new RegExp(`/drafts/${draftId}/publish/$`), { ...previewed, published_at: '2026-10-17T00:00:00Z' });
    server.use(preview.handler, simulation.handler, publish.handler);
    const { user } = renderWithProviders(<ContentWorkbench />);
    await openDraft(user);
    await user.click(screen.getByRole('button', { name: 'Preview changes and audit rewards' }));
    await screen.findByRole('region', { name: 'Exact publication preview' });
    expect(preview.calls[0]).toMatchObject({ url: expect.stringMatching(/\/preview\/$/), body: { revision: 2 } });
    expect(screen.getByText(/Some retained rewards/)).toBeVisible();
    expect(screen.getByRole('button', { name: 'Publish reviewed draft' })).toBeDisabled();
    await user.click(screen.getByRole('button', { name: 'Compare published and draft' }));
    await screen.findByRole('region', { name: 'Published and draft comparison' });
    expect(simulation.calls).toHaveLength(1);
    expect(simulation.calls[0]).toMatchObject({ url: expect.stringMatching(/\/simulate\/$/), body: { revision: 2, preview_id: 'plan-1', config } });
    expect(screen.getAllByText('Not reached')).toHaveLength(2);
    expect(screen.getByText('Private family shop decisions')).toBeVisible();
    await user.click(screen.getByRole('button', { name: 'Publish reviewed draft' }));
    expect(publish.calls).toHaveLength(0);
    await user.click(within(screen.getByRole('alertdialog', { name: 'Publish this reviewed draft?' })).getByRole('button', { name: 'Publish now' }));
    await screen.findByText(/Draft published/);
    expect(publish.calls).toHaveLength(1);
    expect(publish.calls[0]).toMatchObject({ url: expect.stringMatching(/\/publish\/$/), body: { revision: 2, preview_id: 'plan-1', content_digest: 'abc123', confirmation: true } });
  });

  it('invalidates a reviewed preview immediately when the editor changes', async () => {
    setup(metadata, previewed);
    const { user } = renderWithProviders(<ContentWorkbench />);
    await openDraft(user);
    await screen.findByRole('region', { name: 'Exact publication preview' });
    await openChallenge(user);
    fireEvent.change(screen.getByRole('spinbutton', { name: 'Coin reward' }), { target: { value: '90' } });
    expect(screen.queryByRole('region', { name: 'Exact publication preview' })).toBeNull();
    expect(screen.queryByRole('button', { name: 'Publish reviewed draft' })).toBeNull();
    expect(screen.getByRole('button', { name: 'Preview changes and audit rewards' })).toBeDisabled();
  });

  it('removes a saved entry only after confirmation and invalidates its reviewed preview', async () => {
    setup(metadata, previewed);
    const patch = spyHandler('patch', new RegExp(`/api/rpg/content-workbench/drafts/${draftId}/$`), { ...draft, revision: 3 });
    server.use(patch.handler);
    const { user } = renderWithProviders(<ContentWorkbench />);
    await openDraft(user); await openChallenge(user);
    await screen.findByRole('region', { name: 'Exact publication preview' });
    await user.click(screen.getByRole('button', { name: 'Remove from draft' }));
    expect(patch.calls).toHaveLength(0);
    await user.click(within(screen.getByRole('alertdialog', { name: 'Remove this entry from the draft?' })).getByRole('button', { name: 'Remove change' }));
    await screen.findByText(/Entry removed from the draft/);
    expect(patch.calls).toHaveLength(1);
    expect(patch.calls[0]).toMatchObject({ url: expect.stringMatching(new RegExp(`/api/rpg/content-workbench/drafts/${draftId}/$`)), body: { revision: 2, changes: [] } });
    expect(screen.queryByRole('region', { name: 'Exact publication preview' })).toBeNull();
    expect(screen.queryByRole('form', { name: 'Challenge editor' })).toBeNull();
    expect(screen.getByRole('button', { name: /🌲 Forest reading/ })).toHaveTextContent('10 coins');
  });

  it('keeps the exact preview and scenario inputs when a comparison fails and never retries a mutation', async () => {
    setup(metadata, previewed);
    const simulation = spyHandler('post', new RegExp(`/drafts/${draftId}/simulate/$`), HttpResponse.json({ detail: 'Scenario exceeds budget.' }, { status: 400 }));
    server.use(simulation.handler);
    const { user } = renderWithProviders(<ContentWorkbench />);
    await openDraft(user);
    fireEvent.change(screen.getByRole('spinbutton', { name: 'Simulated children' }), { target: { value: '15' } });
    await user.click(screen.getByRole('button', { name: 'Compare published and draft' }));
    await screen.findByText(/Scenario exceeds budget/);
    expect(screen.getByRole('spinbutton', { name: 'Simulated children' })).toHaveValue(15);
    expect(screen.getByRole('region', { name: 'Exact publication preview' })).toBeVisible();
    expect(screen.getByRole('button', { name: 'Publish reviewed draft' })).toBeDisabled();
    expect(simulation.calls).toHaveLength(1);
  });

  it('fences delayed catalog reads when the credential changes', async () => {
    setup();
    let started = false;
    let resolve;
    const waiting = new Promise((done) => { resolve = done; });
    server.use(http.get('*/api/rpg/content-workbench/', async () => { started = true; await waiting; return HttpResponse.json(metadata); }));
    const { user } = renderWithProviders(<AccountSwitcher />);
    await waitFor(() => expect(started).toBe(true));
    await user.click(screen.getByRole('button', { name: 'Switch account' }));
    await act(async () => resolve());
    expect(screen.queryByRole('button', { name: /🌲 Forest reading/ })).toBeNull();
    expect(screen.queryByRole('button', { name: 'Create draft' })).toBeNull();
  });

  it('removes loaded catalog and draft controls if the server revokes designer access', async () => {
    setup(metadata, previewed);
    const simulation = spyHandler('post', new RegExp(`/drafts/${draftId}/simulate/$`), HttpResponse.json({ detail: 'Designer access revoked.' }, { status: 403 }));
    server.use(simulation.handler);
    const { user } = renderWithProviders(<ContentWorkbench />);
    await openDraft(user);
    await user.click(screen.getByRole('button', { name: 'Compare published and draft' }));
    await screen.findByText('RPG content management is available to staff parents.');
    expect(screen.queryByRole('form', { name: 'Draft comparison scenario' })).toBeNull();
    expect(screen.queryByRole('button', { name: /🌲 Forest reading/ })).toBeNull();
    expect(simulation.calls).toHaveLength(1);
  });
});

function AccountSwitcher() {
  const { setUser } = useAuth();
  return <><button type="button" onClick={() => { localStorage.setItem('abby_auth_token', 'other-child-token'); setUser(buildUser({ id: 88 })); }}>Switch account</button><ContentWorkbench /></>;
}
