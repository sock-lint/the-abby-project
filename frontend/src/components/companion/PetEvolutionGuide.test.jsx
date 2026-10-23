import { describe, expect, it } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import { http, HttpResponse } from 'msw';
import PetEvolutionGuide from './PetEvolutionGuide';
import { server } from '../../test/server';
import { renderWithProviders } from '../../test/render';

const creature = { id: 1, species: { slug: 'chick', sprite_key: 'cute-chick' }, potion: { slug: 'base' }, evolution_stage: 'fledgling', growth_points: 65 };

describe('PetEvolutionGuide', () => {
  it('includes the egg before all three owned stages and highlights only the confirmed middle stage', () => {
    render(<PetEvolutionGuide creature={creature} />);
    const steps = within(screen.getByRole('list', { name: 'Pet growth stages' })).getAllByRole('listitem');
    expect(steps).toHaveLength(4);
    expect(steps[0]).toHaveTextContent('Egg');
    expect(steps[0]).not.toHaveAttribute('aria-current');
    expect(steps[1]).not.toHaveAttribute('aria-current');
    expect(steps[1]).toHaveTextContent('Baby');
    expect(steps[2]).toHaveAttribute('aria-current', 'step');
    expect(steps[2]).toHaveTextContent('Middle');
    expect(steps[2]).toHaveTextContent('Fledgling');
    expect(steps[3]).toHaveTextContent('Grown');
    expect(steps[3]).not.toHaveAttribute('aria-current');
  });

  it.each(['fox', 'new-creature'])('shows the complete lifecycle for %s without borrowing Bird forms', (slug) => {
    render(<PetEvolutionGuide creature={{ ...creature, species: { slug, sprite_key: slug }, evolution_stage: null, lifecycle_stage: 'middle' }} />);
    const steps = within(screen.getByRole('list', { name: 'Pet growth stages' })).getAllByRole('listitem');
    expect(steps).toHaveLength(4);
    expect(steps[2]).toHaveAttribute('aria-current', 'step');
    expect(screen.queryByText(/Fledgling|Chick|Bird/)).toBeNull();
  });

  it('shows an inventory egg as the current stage before hatching without inventing owned growth', () => {
    render(<PetEvolutionGuide species={{ name: 'Fox', slug: 'fox' }} currentStage="egg" />);
    const steps = within(screen.getByRole('list', { name: 'Pet growth stages' })).getAllByRole('listitem');
    expect(steps[0]).toHaveAttribute('aria-current', 'step');
    expect(steps[0]).toHaveTextContent(/hatch/i);
    expect(steps[1]).not.toHaveAttribute('aria-current');
  });

  it('keeps the baby stage until a response confirms middle growth and the grown stage until confirmed evolution', () => {
    render(<PetEvolutionGuide creature={{ id: 2, species: { slug: 'fox' }, growth_points: 100, evolved_to_mount: false }} />);
    const steps = within(screen.getByRole('list', { name: 'Pet growth stages' })).getAllByRole('listitem');
    expect(steps[1]).toHaveAttribute('aria-current', 'step');
    expect(steps[3]).not.toHaveAttribute('aria-current');
  });
});

describe('PetEvolutionGuide child surprise', () => {
  const wolf = { slug: 'meshtint-wolf', sprite_key: 'meshtint-wolf', name: 'Wolf' };
  async function asAccount(account, ui) {
    server.use(http.get('*/api/auth/me/', () => HttpResponse.json(account)));
    renderWithProviders(ui);
    return within(await screen.findByRole('list', { name: 'Pet growth stages' }));
  }

  it('keeps generic stages but withholds unreached form names from a child', async () => {
    const guide = await asAccount({ id: 5, role: 'child', is_staff: false },
      <PetEvolutionGuide creature={{ id: 3, species: wolf, potion: { slug: 'base' }, lifecycle_stage: 'baby', growth_points: 99 }} />);
    expect(guide.getAllByRole('listitem')).toHaveLength(4);
    expect(guide.getByText('Baby · Wolf Pup')).toBeInTheDocument();
    expect(guide.getByText('Middle')).toBeInTheDocument();
    expect(guide.getByText('Grown')).toBeInTheDocument();
    expect(screen.queryByText(/Werewolf/)).toBeNull();
    expect(screen.getByText('From 50 growth')).toBeInTheDocument();
  });

  it('reveals only the stages an owned appearance reached', async () => {
    const guide = await asAccount({ id: 5, role: 'child' },
      <PetEvolutionGuide species={wolf} potion={{ slug: 'base' }} currentStage="egg" revealedStages={[]} />);
    expect(guide.getByText('Baby')).toBeInTheDocument();
    expect(screen.queryByText(/Wolf Pup|Werewolf/)).toBeNull();
  });

  it('keeps every form name for parents', async () => {
    const guide = await asAccount({ id: 6, role: 'parent', is_staff: false },
      <PetEvolutionGuide species={wolf} potion={{ slug: 'base' }} currentStage="egg" revealedStages={[]} />);
    expect(guide.getByText('Grown · Werewolf')).toBeInTheDocument();
  });
});
