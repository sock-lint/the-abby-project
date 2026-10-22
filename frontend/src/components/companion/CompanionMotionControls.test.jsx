import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import CompanionMotionControls from './CompanionMotionControls';
import { resolveElementalAppearance } from '../../companion/sharedElementalRelease';
import { stagedElementalFixture, syntheticElemental } from '../../test/elementalReleaseFixture';
import { openDropdown, selectDropdown } from '../../test/selectDropdown';

describe('Elemental logical motion controls', () => {
  it.each(['fire', 'ice'])('selects both %s Dragon idle aliases independently and returns to rest', async (potion) => {
    const user = userEvent.setup(), onPlay = vi.fn();
    const appearance = resolveElementalAppearance(syntheticElemental('meshtint-dragon', potion, 'middle'), 'pet', stagedElementalFixture(true));
    render(<CompanionMotionControls motions={appearance.motions} disabled={false} onPlay={onPlay} />);
    await user.click(screen.getByText('More motions'));
    const picker = screen.getByRole('combobox', { name: 'Companion motion' });
    const list = await openDropdown(user, picker);
    const values = list.getAllByRole('option').map((option) => option.getAttribute('data-value'));
    expect(new Set(values).size).toBe(values.length);
    expect(picker).toHaveValue('idle');
    for (const motion of ['fly-idle', 'idle']) {
      await selectDropdown(user, picker, motion);
      await user.click(screen.getByRole('button', { name: 'Play motion' }));
      expect(onPlay).toHaveBeenLastCalledWith(expect.objectContaining({ id: motion, motion, variantId: 'source-fly-idle' }));
    }
    await user.click(screen.getByRole('button', { name: 'Return to rest' }));
    expect(onPlay).toHaveBeenLastCalledWith({ id: 'idle', label: 'Rest' });
  });
});
