import { describe, expect, it } from 'vitest';
import { http, HttpResponse } from 'msw';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import TestSection from './TestSection.jsx';
import { server } from '../../test/server.js';
import { spyHandler } from '../../test/spy.js';

// Stable defaults — the section calls 5 selector endpoints in parallel
// on mount (children, rewards, items, pet-species, potion-types) plus
// the checklist markdown.
function mountDefaults({
  children = [],
  rewards = [],
  items = [],
  petSpecies = [],
  potionTypes = [],
  checklist = '',
} = {}) {
  server.use(
    http.get('*/api/dev/children/', () => HttpResponse.json(children)),
    http.get('*/api/dev/rewards/', () => HttpResponse.json(rewards)),
    http.get('*/api/dev/items/', () => HttpResponse.json(items)),
    http.get('*/api/dev/pet-species/', () => HttpResponse.json(petSpecies)),
    http.get('*/api/dev/potion-types/', () => HttpResponse.json(potionTypes)),
    http.get('*/api/dev/checklist/', () => HttpResponse.json({ markdown: checklist })),
  );
}

const TWO_KIDS = [
  { id: 1, username: 'abby', display_label: 'Abby', pets: [], mounts: [] },
  { id: 2, username: 'sib',  display_label: 'Sib',  pets: [], mounts: [] },
];

const CHECKLIST_WITH_IDS = `# Manual Testing

## Toast & ceremony reveals

| Surface | Precondition | How | Verify |
|---|---|---|---|
| Approval toast <!-- id:force-approval-notification --> | x | y | z |
| Quest progress <!-- id:force-quest-progress --> | x | y | z |
`;

describe('TestSection', () => {
  it('shows the empty-children state when family has no kids', async () => {
    mountDefaults({ children: [] });
    render(<TestSection />);
    await waitFor(() => {
      expect(screen.getByText(/no children in your family yet/i)).toBeInTheDocument();
    });
  });

  it('renders all 16 cards once children load', async () => {
    mountDefaults({ children: TWO_KIDS });
    render(<TestSection />);
    await screen.findByText(/Force drop/i);

    // Original 8
    expect(screen.getByText(/Force drop/i)).toBeInTheDocument();
    expect(screen.getByText(/Force celebration/i)).toBeInTheDocument();
    expect(screen.getByText(/Set streak/i)).toBeInTheDocument();
    expect(screen.getByText(/Set pet happiness/i)).toBeInTheDocument();
    expect(screen.getByText(/Expire journal entry/i)).toBeInTheDocument();
    expect(screen.getByText(/Set reward stock/i)).toBeInTheDocument();
    expect(screen.getByText(/Reset day counters/i)).toBeInTheDocument();
    expect(screen.getByText(/Tick perfect day/i)).toBeInTheDocument();

    // New 8
    expect(screen.getByText(/Force approval notification/i)).toBeInTheDocument();
    expect(screen.getByText(/Force quest progress/i)).toBeInTheDocument();
    expect(screen.getByText(/Mark daily challenge ready/i)).toBeInTheDocument();
    expect(screen.getByText(/Set pet growth/i)).toBeInTheDocument();
    expect(screen.getByText(/Grant hatch ingredients/i)).toBeInTheDocument();
    expect(screen.getByText(/Clear mount breed cooldowns/i)).toBeInTheDocument();
    expect(screen.getByText(/Seed companion growth/i)).toBeInTheDocument();
    expect(screen.getByText(/Mark expedition ready/i)).toBeInTheDocument();
  });

  it('shows a boot-error empty state when ALL selector endpoints fail', async () => {
    server.use(
      http.get('*/api/dev/children/',     () => new HttpResponse(null, { status: 403 })),
      http.get('*/api/dev/rewards/',      () => new HttpResponse(null, { status: 403 })),
      http.get('*/api/dev/items/',        () => new HttpResponse(null, { status: 403 })),
      http.get('*/api/dev/pet-species/',  () => new HttpResponse(null, { status: 403 })),
      http.get('*/api/dev/potion-types/', () => new HttpResponse(null, { status: 403 })),
      http.get('*/api/dev/checklist/',    () => new HttpResponse(null, { status: 403 })),
    );
    render(<TestSection />);
    await waitFor(() => {
      expect(screen.getByText(/could not reach \/api\/dev/i)).toBeInTheDocument();
    });
  });

  it('Target dropdown renders one <option> per child (regression — was empty)', async () => {
    // The original bug: <SelectField options={array}> silently ignored
    // the options prop because the primitive expects <option> children.
    // After the fix, the Target select must list every kid.
    mountDefaults({ children: TWO_KIDS });
    render(<TestSection />);

    const heading = await screen.findByText('Force drop');
    const card = heading.closest('div').parentElement;
    const targetSelect = within(card)
      .getByText(/^target$/i)
      .parentElement.querySelector('select');

    const opts = targetSelect.querySelectorAll('option');
    expect(opts).toHaveLength(2);
    expect(opts[0]).toHaveTextContent('Abby');
    expect(opts[1]).toHaveTextContent('Sib');
  });

  it('Force drop card POSTs to /api/dev/force-drop/ with the form values', async () => {
    mountDefaults({ children: [{ id: 7, username: 'abby', display_label: 'Abby', pets: [], mounts: [] }] });

    const calls = [];
    server.use(
      http.post('*/api/dev/force-drop/', async ({ request }) => {
        const body = await request.json();
        calls.push({ body });
        return HttpResponse.json({
          user: 'abby',
          item: { id: 1, slug: 'lucky-coin', name: 'Lucky Coin', rarity: 'legendary' },
          count: 1,
          salvaged: false,
        });
      }),
    );

    const user = userEvent.setup();
    render(<TestSection />);

    const dropCard = (await screen.findByText('Force drop')).closest('div').parentElement;
    const fire = within(dropCard).getByRole('button', { name: /drop it/i });
    await user.click(fire);

    await waitFor(() => expect(calls).toHaveLength(1));
    expect(calls[0].body.user_id).toBe(7);
    expect(calls[0].body.rarity).toBe('legendary');
    expect(calls[0].body.salvage).toBe(false);
  });

  it('Force approval notification card sends the right body shape', async () => {
    mountDefaults({ children: [{ id: 7, username: 'abby', display_label: 'Abby', pets: [], mounts: [] }] });
    const spy = spyHandler(
      'post',
      /\/api\/dev\/force-approval-notification\/$/,
      { notification_type: 'chore_approved', notification_id: 99 },
    );
    server.use(spy.handler);

    const user = userEvent.setup();
    render(<TestSection />);

    const heading = await screen.findByText('Force approval notification');
    const card = heading.closest('div').parentElement;
    const send = within(card).getByRole('button', { name: /^send$/i });
    await user.click(send);

    await waitFor(() => expect(spy.calls).toHaveLength(1));
    expect(spy.calls[0].body).toEqual({
      user_id: 7,
      flow: 'chore',
      outcome: 'approved',
      note: '',
    });
  });

  it('Force quest progress card sends the default delta', async () => {
    mountDefaults({ children: [{ id: 7, username: 'abby', display_label: 'Abby', pets: [], mounts: [] }] });
    const spy = spyHandler(
      'post',
      /\/api\/dev\/force-quest-progress\/$/,
      {
        quest_id: 1,
        definition_name: 'Test Boss',
        current_progress: 10,
        target_value: 100,
        progress_percent: 10.0,
        delta: 10,
      },
    );
    server.use(spy.handler);

    const user = userEvent.setup();
    render(<TestSection />);

    const heading = await screen.findByText('Force quest progress');
    const card = heading.closest('div').parentElement;
    const bump = within(card).getByRole('button', { name: /^bump$/i });
    await user.click(bump);

    await waitFor(() => expect(spy.calls).toHaveLength(1));
    expect(spy.calls[0].body).toEqual({ user_id: 7, delta: 10 });
  });

  it('Mark expedition ready card sends the default tier', async () => {
    mountDefaults({ children: [{ id: 7, username: 'abby', display_label: 'Abby', pets: [], mounts: [] }] });
    const spy = spyHandler(
      'post',
      /\/api\/dev\/mark-expedition-ready\/$/,
      {
        expedition_id: 1,
        mount_id: null,
        species_name: 'Fox',
        tier: 'standard',
        ready_at: '2026-05-11T00:00:00Z',
        coins: 35,
        item_count: 2,
      },
    );
    server.use(spy.handler);

    const user = userEvent.setup();
    render(<TestSection />);

    const heading = await screen.findByText('Mark expedition ready');
    const card = heading.closest('div').parentElement;
    const fire = within(card).getByRole('button', { name: /run \+ ready/i });
    await user.click(fire);

    await waitFor(() => expect(spy.calls).toHaveLength(1));
    expect(spy.calls[0].body).toEqual({ user_id: 7, tier: 'standard' });
  });

  it('Mark verified flips the linked checklist row', async () => {
    mountDefaults({
      children: TWO_KIDS,
      checklist: CHECKLIST_WITH_IDS,
    });
    server.use(
      spyHandler(
        'post',
        /\/api\/dev\/force-approval-notification\/$/,
        { notification_type: 'chore_approved', notification_id: 99 },
      ).handler,
    );

    const user = userEvent.setup();
    render(<TestSection />);

    const heading = await screen.findByText('Force approval notification');
    const card = heading.closest('div').parentElement;

    // Fire the card so the result line + Mark verified button render.
    const send = within(card).getByRole('button', { name: /^send$/i });
    await user.click(send);

    const markBtn = await within(card).findByRole('button', {
      name: /mark verified/i,
    });

    // The matching row in the checklist starts unchecked. The checkbox
    // carries an aria-label of "<section> — <label>" per ChecklistRail's
    // existing convention.
    const rowCheckbox = await screen.findByRole('checkbox', {
      name: /approval toast/i,
    });
    expect(rowCheckbox).not.toBeChecked();

    await user.click(markBtn);

    await waitFor(() => expect(rowCheckbox).toBeChecked());
    // Button is replaced by the script-tone "marked verified" text.
    expect(within(card).getByText(/marked verified/i)).toBeInTheDocument();
  });
});
