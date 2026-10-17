import { describe, expect, it, vi } from 'vitest';
import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { renderWithProviders } from '../../test/render';
import FamilyStagePreview from './FamilyStagePreview';
import { rosterEgg } from '../../test/rosterReleaseFixture';

describe('Hatchery family stage previews', () => {
  it('previews all four exact family stages without loading a model or changing owned progression', async () => {
    const user = userEvent.setup(), fetch = vi.spyOn(globalThis, 'fetch');
    renderWithProviders(<FamilyStagePreview item={{ ...rosterEgg(), name: 'Wolf Egg' }} />, { withAuth: false });
    expect(screen.getByRole('button', { name: 'Egg' })).toHaveAttribute('aria-pressed', 'true');
    for (const [stage, name] of [['Baby', 'Wolf Pup'], ['Middle', 'Wolf'], ['Grown', 'Werewolf']]) {
      await user.click(screen.getByRole('button', { name: stage }));
      expect(screen.getByRole('heading', { name })).toBeInTheDocument();
    }
    expect(fetch.mock.calls.filter(([url, options]) => String(url).endsWith('.glb') || options?.method === 'POST')).toHaveLength(0);
    fetch.mockRestore();
  });

  it('never turns a conflicting or Dummy egg into a roster preview', () => {
    renderWithProviders(<FamilyStagePreview item={{ ...rosterEgg(), pet_species_slug: 'meshtint-training-dummy' }} />, { withAuth: false });
    expect(screen.queryByRole('button', { name: 'Baby' })).toBeNull();
    expect(screen.queryByRole('button', { name: 'Show 3D preview' })).toBeNull();
  });
});
