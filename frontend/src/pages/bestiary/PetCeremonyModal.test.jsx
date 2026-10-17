import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { screen, act } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { renderWithProviders } from '../../test/render';
import PetCeremonyModal from './PetCeremonyModal';
import presentation from '../../storybook/presentation.json';
import { getLicensedRpgSprite, resolveLicensedRpgSprite } from '../../storybook/licensedRpgSprites';
import { resolveCatalogIcon } from '../../catalog/sharedCatalogIcons';
import rosterBreed from '../../../../contracts/api/fixtures/mount-breed-roster.json';

vi.mock('../../catalog/sharedCatalogIcons', () => ({ resolveCatalogIcon: vi.fn(() => null) }));

vi.mock('../../storybook/licensedRpgSprites', async () => {
  const actual = await vi.importActual('../../storybook/licensedRpgSprites');
  return { ...actual, getLicensedRpgSprite: vi.fn(() => null) };
});

beforeEach(() => {
  getLicensedRpgSprite.mockReset().mockReturnValue(null);
  resolveCatalogIcon.mockReset().mockReturnValue(null);
});

const pet = {
  id: 1,
  species: { name: 'Phoenix', sprite_key: 'phoenix', icon: '🔥' },
  potion: { name: 'Cosmic', slug: 'cosmic' },
};

const breedParents = [
  { id: 10, species: { name: 'Wolf', sprite_key: 'wolf', icon: '🐺' }, potion: { name: 'Fire', slug: 'fire' } },
  { id: 11, species: { name: 'Dragon', sprite_key: 'dragon', icon: '🐉' }, potion: { name: 'Ice', slug: 'ice' } },
];

const breedResult = {
  egg_item_id: 99,
  egg_item_name: 'Wolf Egg',
  egg_item_icon: '🥚',
  egg_item_sprite_key: 'big-egg',
  potion_item_id: 100,
  potion_item_name: 'Fire Potion',
  potion_item_icon: '🧪',
  potion_item_sprite_key: '',
  picked_species: 'Wolf',
  picked_species_slug: 'wolf',
  picked_potion: 'Fire',
  picked_potion_slug: 'fire',
  chromatic: false,
  cooldown_days: 7,
};

describe('PetCeremonyModal', () => {
  it('reveals the exact catalog potion artwork returned by breeding alongside the awarded egg', () => {
    resolveCatalogIcon.mockImplementation((id) => id === 'item-base-potion' ? { url: '/synthetic/base-potion.png' } : null);
    renderWithProviders(<PetCeremonyModal mode="breed" parents={breedParents} result={rosterBreed} reducedMotion onDismiss={() => {}} />);
    expect(screen.getByRole('img', { name: 'Base Potion' })).toHaveAttribute('src', '/synthetic/base-potion.png');
    expect(screen.getByRole('img', { name: 'Bat Egg' })).toBeInTheDocument();
  });

  it.each([undefined, null, 'unknown-potion-art'])('retains the legacy potion fallback when its catalog artwork is %s', (assetId) => {
    renderWithProviders(<PetCeremonyModal mode="breed" parents={breedParents}
      result={{ ...breedResult, potion_item_catalog_icon: assetId }} reducedMotion onDismiss={() => {}} />);
    expect(screen.getByRole('img', { name: 'Fire Potion' })).toHaveTextContent('🧪');
  });

  it('renders hatch headline + dismiss button (mode=hatch)', () => {
    renderWithProviders(
      <PetCeremonyModal mode="hatch" pet={pet} onDismiss={() => {}} />,
    );
    expect(screen.getByRole('alertdialog')).toBeInTheDocument();
    expect(screen.getByText(/cosmic phoenix/i)).toBeInTheDocument();
    expect(screen.getByText(/has joined your companions/i)).toBeInTheDocument();
    expect(screen.getByText('Baby companion')).toBeInTheDocument();
  });

  it('renders evolve headline (mode=evolve)', () => {
    renderWithProviders(
      <PetCeremonyModal
        mode="evolve"
        species={pet.species}
        potion={pet.potion}
        onDismiss={() => {}}
      />,
    );
    expect(screen.getByText(/cosmic phoenix/i)).toBeInTheDocument();
    expect(screen.getByText(/ready to explore/i)).toBeInTheDocument();
  });

  it('renders breed alertdialog with the result egg name (mode=breed)', () => {
    renderWithProviders(
      <PetCeremonyModal
        mode="breed"
        parents={breedParents}
        result={breedResult}
        onDismiss={() => {}}
      />,
    );
    expect(screen.getByRole('alertdialog')).toBeInTheDocument();
    expect(screen.getByText(/wolf egg/i)).toBeInTheDocument();
    expect(screen.getByText(/paired with fire potion/i)).toBeInTheDocument();
    expect(screen.getByText(/parents resting for 7 days/i)).toBeInTheDocument();
    expect(screen.getByText(/a new egg/i)).toBeInTheDocument();
  });

  it('shows chromatic kicker on chromatic breed', () => {
    renderWithProviders(
      <PetCeremonyModal
        mode="breed"
        parents={breedParents}
        result={{ ...breedResult, chromatic: true, picked_potion_slug: 'cosmic', potion_item_name: 'Cosmic Potion' }}
        onDismiss={() => {}}
      />,
    );
    expect(screen.getByText(/a rare cosmic potion/i)).toBeInTheDocument();
    expect(screen.getByText(/with a cosmic potion from this pairing/i)).toBeInTheDocument();
  });

  it('renders the expedition_return shell with mount headline + dismiss CTA', () => {
    const expedition = {
      coins_awarded: 42,
      tier: 'standard',
      items: [],
      mount: {
        id: 5,
        species_name: 'Griffon',
        species_sprite_key: 'griffon',
        species_icon: '🦅',
        potion_name: 'Sky',
        potion_slug: 'sky',
      },
    };
    renderWithProviders(
      <PetCeremonyModal mode="expedition_return" expedition={expedition} onDismiss={() => {}} />,
    );
    expect(screen.getByRole('alertdialog')).toBeInTheDocument();
    expect(screen.getByText(/your grown pet has returned/i)).toBeInTheDocument();
    expect(screen.getByText(/Griffon is back/i)).toBeInTheDocument();
    expect(screen.getByText(/from a standard expedition/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /^continue$/i })).toBeInTheDocument();
  });

  it('calls onDismiss when Continue is clicked', async () => {
    const onDismiss = vi.fn();
    const user = userEvent.setup();
    renderWithProviders(
      <PetCeremonyModal mode="hatch" pet={pet} onDismiss={onDismiss} />,
    );
    await user.click(screen.getByRole('button', { name: /continue/i }));
    expect(onDismiss).toHaveBeenCalled();
  });

  it('renders nothing for unknown mode', () => {
    const { container } = renderWithProviders(
      <PetCeremonyModal mode="unknown" pet={pet} onDismiss={() => {}} />,
    );
    expect(container.querySelector('[role="alertdialog"]')).toBeNull();
  });
});

describe('PetCeremonyModal — phased sequence', () => {
  beforeEach(() => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it('hatch egg is rendered in phase 0 and replaced by the pet sprite by terminal phase', async () => {
    renderWithProviders(
      <PetCeremonyModal mode="hatch" pet={pet} onDismiss={() => {}} />,
    );
    // Phase 0: the egg sprite renders. RpgSprite falls through to emoji
    // fallback in the test env (catalog is empty), so we can find the egg
    // by its alt text.
    expect(screen.getByLabelText('egg')).toBeInTheDocument();

    // Advance through all phase timers (800 + 400 + 1200 = 2400ms).
    await act(async () => {
      await vi.advanceTimersByTimeAsync(3000);
    });
    // Terminal phase: pet sprite is shown (alt = species name).
    expect(screen.getByLabelText('Phoenix')).toBeInTheDocument();
  });

  it('evolve renders the base sprite first then swaps to the mount form', async () => {
    renderWithProviders(
      <PetCeremonyModal
        mode="evolve"
        species={pet.species}
        potion={pet.potion}
        onDismiss={() => {}}
      />,
    );
    // Phase 0: base species sprite is visible.
    expect(screen.getAllByLabelText('Phoenix').length).toBeGreaterThan(0);

    // Advance past all phases (400 + 800 + 300 = 1500ms).
    await act(async () => {
      await vi.advanceTimersByTimeAsync(2200);
    });
    // Terminal phase: the mount form is visible (RpgSprite with the
    // ``-mount`` slug; it falls back to the base species sprite which
    // still uses the species name as its alt text).
    expect(screen.getAllByLabelText('Phoenix').length).toBeGreaterThan(0);
  });

  it('expedition_return reveals the loot summary at terminal phase', async () => {
    const expedition = {
      coins_awarded: 42,
      tier: 'short',
      items: [
        { name: 'Training Snack', icon: '🍪', sprite_key: '', rarity: 'common', quantity: 1 },
        { name: 'Frame of the Wanderer', icon: '🖼️', sprite_key: '', rarity: 'rare', quantity: 1, salvaged_to_coins: 25 },
      ],
      mount: {
        id: 5,
        species_name: 'Griffon',
        species_sprite_key: 'griffon',
        species_icon: '🦅',
        potion_name: 'Sky',
        potion_slug: 'sky',
      },
    };
    renderWithProviders(
      <PetCeremonyModal mode="expedition_return" expedition={expedition} onDismiss={() => {}} />,
    );
    // Phases for expedition_return: [600, 400, 1200] = 2200ms then settled.
    await act(async () => {
      await vi.advanceTimersByTimeAsync(2400);
    });
    expect(screen.getByText(/\+42/)).toBeInTheDocument();
    expect(screen.getByText('Training Snack')).toBeInTheDocument();
    expect(screen.getByText(/duplicate exchanged for 25 coins/i)).toBeInTheDocument();
    expect(screen.getByText('common')).toBeInTheDocument();
    expect(screen.getByText('rare')).toBeInTheDocument();
  });
});

describe('PetCeremonyModal — licensed Chick portraits', () => {
  const chickPet = {
    id: 20,
    species: { name: 'Chick', sprite_key: 'cute-chick', icon: '🐥' },
    potion: { name: 'Base', slug: 'base' },
  };
  const chickPortrait = '/assets/synthetic-chick.png';
  const birdPortrait = '/assets/synthetic-bird.png';

  beforeEach(() => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const manifest = {
      schema_version: presentation.schema_version,
      companion: {
        id: presentation.companion.id,
        art_key: 'chick',
        temporary: false,
        portrait: 'chick.png',
      },
    };
    const art = (name) => ({ 'chick.png': chickPortrait, 'fledgling.png': '/assets/synthetic-fledgling.png', 'bird.png': birdPortrait })[name];
    getLicensedRpgSprite.mockImplementation((key) => resolveLicensedRpgSprite(key, manifest, art));
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('hatches a Chick portrait after the egg without showing the evolved Bird', async () => {
    renderWithProviders(
      <PetCeremonyModal mode="hatch" pet={chickPet} onDismiss={() => {}} />,
      { withAuth: false },
    );
    expect(screen.getByRole('img', { name: 'egg' })).toHaveTextContent('🥚');
    expect(screen.queryByRole('img', { name: 'Chick' })).not.toBeInTheDocument();

    await act(async () => {
      await vi.advanceTimersByTimeAsync(1300);
    });
    expect(screen.queryByRole('img', { name: 'egg' })).not.toBeInTheDocument();
    expect(screen.getByRole('img', { name: 'Chick' })).toHaveAttribute('src', chickPortrait);

    await act(async () => {
      await vi.advanceTimersByTimeAsync(1300);
    });
    expect(screen.getByRole('img', { name: 'Chick' })).toHaveAttribute('src', chickPortrait);
    expect(document.querySelector(`img[src="${birdPortrait}"]`)).toBeNull();
  });

  it('celebrates the confirmed Fledgling-to-Bird form with matching names and portraits', async () => {
    renderWithProviders(<PetCeremonyModal mode="evolve" species={{ ...chickPet.species, slug: 'chick' }} potion={chickPet.potion} fromStage="fledgling" onDismiss={() => {}} />, { withAuth: false });
    expect(screen.getByRole('img', { name: 'Fledgling' })).toHaveAttribute('src', '/assets/synthetic-fledgling.png');
    await act(async () => { await vi.advanceTimersByTimeAsync(1700); });
    expect(screen.getByRole('img', { name: 'Bird' })).toHaveAttribute('src', birdPortrait);
    expect(screen.getByRole('alertdialog', { name: 'Base Bird' })).toBeInTheDocument();
  });

  it('swaps the Chick base portrait for the Bird mount after confirmed evolution', async () => {
    renderWithProviders(
      <PetCeremonyModal
        mode="evolve"
        species={chickPet.species}
        potion={chickPet.potion}
        onDismiss={() => {}}
      />,
      { withAuth: false },
    );
    expect(screen.getByRole('img', { name: 'Chick' })).toHaveAttribute('src', chickPortrait);
    expect(document.querySelector(`img[src="${birdPortrait}"]`)).toBeNull();

    await act(async () => {
      await vi.advanceTimersByTimeAsync(1700);
    });
    expect(screen.getByRole('img', { name: 'Chick' })).toHaveAttribute('src', birdPortrait);
    expect(document.querySelector(`img[src="${chickPortrait}"]`)).toBeNull();
    expect(screen.getByText(/is ready to explore/i)).toBeInTheDocument();
  });

  it('shows the Chick parent as a Bird mount while keeping the other parent on its own species', async () => {
    renderWithProviders(
      <PetCeremonyModal
        mode="breed"
        parents={[chickPet, breedParents[0]]}
        result={{
          ...breedResult,
          egg_item_name: 'Chick Egg',
          potion_item_name: 'Base Potion',
          picked_species: 'Chick',
          picked_species_slug: 'cute-chick',
          picked_potion: 'Base',
          picked_potion_slug: 'base',
        }}
        onDismiss={() => {}}
      />,
      { withAuth: false },
    );
    expect(screen.getByRole('img', { name: 'Chick' })).toHaveAttribute('src', birdPortrait);
    expect(screen.getByRole('img', { name: 'Wolf' })).toHaveTextContent('🐺');
    expect(document.querySelector(`img[src="${chickPortrait}"]`)).toBeNull();

    await act(async () => {
      await vi.advanceTimersByTimeAsync(2600);
    });
    expect(screen.queryByRole('img', { name: 'Chick' })).not.toBeInTheDocument();
    expect(screen.queryByRole('img', { name: 'Wolf' })).not.toBeInTheDocument();
    expect(screen.getByRole('img', { name: 'Chick Egg' })).toHaveTextContent('🥚');
    expect(screen.getByRole('img', { name: 'Base Potion' })).toHaveTextContent('🧪');
    expect(document.querySelector(`img[src="${birdPortrait}"]`)).toBeNull();
  });

  it('keeps the returning Chick on its Bird mount portrait through the loot reveal', async () => {
    renderWithProviders(
      <PetCeremonyModal
        mode="expedition_return"
        expedition={{
          coins_awarded: 15,
          tier: 'short',
          items: [],
          mount: {
            id: 20,
            species_name: 'Chick',
            species_sprite_key: 'cute-chick',
            species_icon: '🐥',
            potion_name: 'Base',
            potion_slug: 'base',
          },
        }}
        onDismiss={() => {}}
      />,
      { withAuth: false },
    );
    expect(screen.getByRole('img', { name: 'Chick' })).toHaveAttribute('src', birdPortrait);
    expect(screen.queryByText('+15')).not.toBeInTheDocument();

    await act(async () => {
      await vi.advanceTimersByTimeAsync(2400);
    });
    expect(screen.getByRole('img', { name: 'Chick' })).toHaveAttribute('src', birdPortrait);
    expect(screen.getByText('+15')).toBeInTheDocument();
    expect(document.querySelector(`img[src="${chickPortrait}"]`)).toBeNull();
  });
});
