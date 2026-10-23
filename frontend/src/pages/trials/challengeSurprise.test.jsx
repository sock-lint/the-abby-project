import { describe, expect, it, vi } from 'vitest';
import { http, HttpResponse, delay } from 'msw';
import { screen, waitFor } from '@testing-library/react';
import { renderWithProviders } from '../../test/render';
import { server } from '../../test/server';
import { buildParent, buildUser } from '../../test/factories';
import { buildChallengeGoal } from '../../test/challenges';
import { useAuth } from '../../hooks/useApi';
import ChallengeGoalCard, { ChallengeGoalDetail } from './ChallengeGoalCard';
import PinnedChallengeCard from '../../components/dashboard/PinnedChallengeCard';
import BonusChallengeBrowser from './BonusChallengeBrowser';

// The owner's child surprise rule on challenges: an elemental challenge's
// illustration depicts its Baby companion, so a child sees it only once that
// exact appearance hatched. Only the private artwork lookup is synthetic.
vi.mock('../../companion/sharedElementalPortraits', async (original) => ({
  ...await original(),
  resolveElementalCatalogIcon: (id) => /^(challenge-|review-)/.test(id || '') ? { url: `/synthetic/${id}.png`, frames: 1 } : null,
}));

const wolf = { id: 3, slug: 'meshtint-wolf', name: 'Wolf Pup', sprite_key: 'meshtint-wolf' };
const dragon = { id: 4, slug: 'meshtint-dragon', name: 'Dragon Spark', sprite_key: 'meshtint-dragon' };
const potion = (slug) => ({ id: { base: 1, fire: 2, ice: 3 }[slug], slug, name: slug[0].toUpperCase() + slug.slice(1) });
const pet = (species, slug, lifecycle_stage = 'baby', over = {}) => ({ id: 70, species, potion: potion(slug), lifecycle_stage,
  growth_points: lifecycle_stage === 'baby' ? 5 : 60, evolved_to_mount: false, ...over });
const emberTrail = buildChallengeGoal({ id: 'goal:31', name: 'Ember Trail', origin: 'catalog', catalog_icon: 'challenge-ember-trail',
  description: 'Discover a Fire Wolf Pup: finish 20 approved chores. Earn one Wolf Pup Egg and one Fire potion.' });
const child = buildUser({ id: 41, is_staff: false });

function Ready({ children }) {
  const { user, loading } = useAuth();
  return loading || !user ? null : children;
}
function mount(surface, { account = child, pets = [], mounts = [], goal = emberTrail, stable } = {}) {
  server.use(
    http.get('*/api/auth/me/', () => HttpResponse.json(account)),
    http.get('*/api/pets/stable/', stable || (() => HttpResponse.json({ pets, mounts }))),
  );
  const ui = typeof surface !== 'string' ? surface : surface === 'detail' ? <ChallengeGoalDetail goal={goal} onClose={() => {}} />
    : surface === 'today' ? <PinnedChallengeCard goal={goal} /> : <ChallengeGoalCard goal={goal} onSelect={() => {}} />;
  return renderWithProviders(<Ready>{ui}</Ready>);
}
const art = () => document.querySelector('img[src^="/synthetic/"]');

describe('Challenge illustrations under the child surprise rule', () => {
  it.each(['card', 'detail', 'today'])('never shows an unhatched appearance on the %s, even while ownership loads', async (surface) => {
    let reads = 0;
    mount(surface, { stable: async () => { reads += 1; await delay(50); return HttpResponse.json({ pets: [], mounts: [] }); } });
    expect(await screen.findByText('Ember Trail')).toBeInTheDocument();
    expect(art()).toBeNull();
    await waitFor(() => expect(reads).toBe(1));
    await delay(80);
    expect(art()).toBeNull();
  });

  it.each([
    ['a hatched Fire Wolf Pup', [pet(wolf, 'fire')], true],
    ['a grown Fire Wolf', [pet(wolf, 'fire', 'grown', { evolved_to_mount: true })], true],
    ['only a grown Base Wolf', [pet(wolf, 'base', 'grown', { evolved_to_mount: true })], false],
    ['an Ice Wolf Pup', [pet(wolf, 'ice')], false],
    ['a Fire pet of another species', [pet(dragon, 'fire')], false],
    ['a Fire Wolf with a legacy blank potion slug', [{ ...pet(wolf, 'fire'), potion: { id: 9, slug: '' } }], false],
  ])('shows the illustration only for the exact appearance: %s', async (_name, pets, visible) => {
    mount('card', { pets });
    expect(await screen.findByText('Ember Trail')).toBeInTheDocument();
    if (visible) await waitFor(() => expect(art()).toHaveAttribute('src', '/synthetic/challenge-ember-trail.png'));
    else {
      await delay(80);
      expect(art()).toBeNull();
    }
  });

  it('keeps the illustration hidden when ownership cannot be read', async () => {
    mount('detail', { stable: () => HttpResponse.json({ detail: 'Unavailable' }, { status: 503 }) });
    expect(await screen.findByRole('dialog', { name: 'Ember Trail' })).toBeInTheDocument();
    await delay(80);
    expect(art()).toBeNull();
  });

  it.each([
    ['parent', buildParent({ id: 42, is_staff: false })],
    ['staff child', buildUser({ id: 43, is_staff: true })],
  ])('keeps every illustration for a %s on each surface', async (_name, account) => {
    for (const surface of ['card', 'detail', 'today']) {
      const view = mount(surface, { account });
      await waitFor(() => expect(art()).toHaveAttribute('src', '/synthetic/challenge-ember-trail.png'));
      view.unmount();
    }
  });

  it.each([
    ['review-bee-fire-acquisition-icon', 'meshtint-bee', 'fire'], ['review-bee-ice-acquisition-icon', 'meshtint-bee', 'ice'],
    ['review-bat-fire-acquisition-icon', 'meshtint-bat', 'fire'], ['review-bat-ice-acquisition-icon', 'meshtint-bat', 'ice'],
  ])('gates the %s acquisition illustration by its exact appearance', async (icon, slug, variant) => {
    const species = { id: 6, slug, name: slug, sprite_key: slug };
    const goal = buildChallengeGoal({ id: `goal:${icon}`, name: icon, origin: 'catalog', catalog_icon: icon });
    const view = mount('card', { goal, pets: [pet(species, variant === 'fire' ? 'ice' : 'fire')] });
    expect(await screen.findByText(icon, { selector: 'h4' })).toBeInTheDocument();
    await delay(80);
    expect(art()).toBeNull();
    view.unmount();
    mount('card', { goal, pets: [pet(species, variant)] });
    await waitFor(() => expect(art()).toHaveAttribute('src', `/synthetic/${icon}.png`));
  });

  it('leaves ordinary challenge artwork alone', async () => {
    mount('card', { goal: buildChallengeGoal({ name: 'Cold Snap', origin: 'catalog', catalog_icon: 'challenge-cold-snap' }) });
    await waitFor(() => expect(art()).toHaveAttribute('src', '/synthetic/challenge-cold-snap.png'));
  });
});

describe('Challenge copy that names an unreached form', () => {
  const shadow = buildChallengeGoal({ id: 'goal:32', name: 'Shadow Trail', origin: 'catalog', catalog_icon: null,
    description: 'Welcome an epic Egglet companion and help it grow into Shadow: finish 25 approved chores. Earn one Egglet Egg.' });
  const egglet = { id: 5, slug: 'meshtint-shadow', name: 'Egglet', sprite_key: 'meshtint-shadow' };

  it('opens with the requirement for a child who has not grown that companion', async () => {
    mount('detail', { goal: shadow, pets: [pet(egglet, 'base', 'middle')] });
    expect(await screen.findByText('Finish 25 approved chores. Earn one Egglet Egg.')).toBeInTheDocument();
    expect(screen.queryByText(/grow into Shadow/)).toBeNull();
  });

  it('keeps the full description once the child reached the named form, and for parents', async () => {
    const grown = pet(egglet, 'base', 'grown', { evolved_to_mount: true });
    const view = mount('detail', { goal: shadow, pets: [grown] });
    expect(await screen.findByText(/help it grow into Shadow/)).toBeInTheDocument();
    view.unmount();
    mount('detail', { goal: shadow, account: buildParent({ id: 44 }) });
    expect(await screen.findByText(/help it grow into Shadow/)).toBeInTheDocument();
  });

  it('does not rewrite a parent-authored goal that shares the name', async () => {
    mount('detail', { goal: { ...shadow, origin: 'parent' } });
    expect(await screen.findByText(/help it grow into Shadow/)).toBeInTheDocument();
  });
});

describe('Shared ownership read and challenge search', () => {
  it('reads the stable once for several companion cards mounted together', async () => {
    let reads = 0;
    const goals = ['challenge-ember-trail', 'challenge-frost-trail', 'challenge-ember-nest'].map((icon, index) =>
      buildChallengeGoal({ id: `goal:${40 + index}`, name: `Card ${index}`, origin: 'catalog', catalog_icon: icon }));
    mount(<>{goals.map((goal) => <ChallengeGoalCard key={goal.id} goal={goal} onSelect={() => {}} />)}</>, {
      stable: async () => { reads += 1; await delay(30); return HttpResponse.json({ pets: [], mounts: [] }); },
    });
    expect(await screen.findByText('Card 2', { selector: 'h4' })).toBeInTheDocument();
    await waitFor(() => expect(reads).toBe(1));
    await delay(80);
    expect(reads).toBe(1);
  });

  it('does not let a child search find a withheld form name', async () => {
    const summit = buildChallengeGoal({ id: 'goal:50', name: 'Ember Summit', origin: 'catalog', catalog_icon: 'challenge-ember-summit',
      description: 'Discover a Fire Dragonling: finish 50 approved chores. Earn one Dragon Spark Egg and one Fire potion.' });
    const browser = <BonusChallengeBrowser goals={[summit]} renderCards={(rows) => rows.map((goal) => <p key={goal.id}>Result {goal.name}</p>)} />;
    const view = mount(browser);
    const { user } = view;
    await user.type(await screen.findByRole('searchbox', { name: 'Search bonus challenges' }), 'Dragonling');
    await delay(80);
    expect(screen.queryByText('Result Ember Summit')).toBeNull();
    await user.clear(screen.getByRole('searchbox', { name: 'Search bonus challenges' }));
    await user.type(screen.getByRole('searchbox', { name: 'Search bonus challenges' }), 'Dragon Spark Egg');
    expect(await screen.findByText('Result Ember Summit')).toBeInTheDocument();
    view.unmount();
    const parent = mount(browser, { account: buildParent({ id: 45 }) });
    await parent.user.type(await screen.findByRole('searchbox', { name: 'Search bonus challenges' }), 'Dragonling');
    expect(await screen.findByText('Result Ember Summit')).toBeInTheDocument();
  });
});
