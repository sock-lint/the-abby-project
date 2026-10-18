import { describe, expect, it, vi } from 'vitest';
import { screen } from '@testing-library/react';
import { renderWithProviders, userEvent } from '../../test/render';
import ArtworkShowcase from './ArtworkShowcase';
import { selectDropdown } from '../../test/selectDropdown';

vi.mock('../../components/rpg/ArtworkImage', () => ({
  default: ({ assetId, size }) => <span data-testid="artwork" data-asset={assetId} data-size={size} />,
}));

describe('artwork inspection gallery', () => {
  it('makes every delivered identity inspectable at actual UI sizes without enabling catalog content', async () => {
    const user = userEvent.setup();
    renderWithProviders(<ArtworkShowcase />);
    const group = screen.getByRole('combobox', { name: 'Artwork group' });
    const size = screen.getByRole('combobox', { name: 'Artwork size' });
    let total = 0;
    for (const [key, count] of [['badges', 182], ['categories', 14], ['subjects', 34], ['skills', 96], ['items', 33], ['challenges', 5], ['birthday', 1]]) {
      await selectDropdown(user, group, key);
      expect(screen.getAllByTestId('artwork')).toHaveLength(count);
      total += count;
    }
    expect(total).toBe(365);
    for (const value of [24, 32, 40, 64, 96]) {
      await selectDropdown(user, size, String(value));
      expect(screen.getByTestId('artwork')).toHaveAttribute('data-size', String(value));
    }
    expect(screen.getByText('Birthday candle')).toBeVisible();
    await user.click(screen.getByText('Integration and accessory limits'));
    expect(screen.getByText(/Acquisition and equipping remain disabled/)).toBeVisible();
    expect(screen.queryByRole('button', { name: /equip|buy|unlock/i })).not.toBeInTheDocument();
  });
});
