import { describe, expect, it, vi } from 'vitest';
import { renderWithProviders, screen, userEvent } from '../../test/render';
import SavedCosmetics from './SavedCosmetics';

describe('SavedCosmetics', () => {
  it('routes an earlier selected cover to the single theme picker without a remove action', () => {
    const cover = { id: 7, name: 'Hyrule Day', icon: '📖', item_type: 'cosmetic_theme', metadata: { theme: 'hyrule' }, catalog_available: false };
    renderWithProviders(<SavedCosmetics cosmetics={{ active_theme: [cover] }} profile={{ active_theme: cover }} onRemove={vi.fn()} />);
    expect(screen.getByText('Memory Meadow')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Change color theme' })).toHaveAttribute('href', '/settings#appearance');
    expect(screen.queryByRole('button', { name: 'Remove previous selection' })).toBeNull();
  });

  it('keeps removal available for an earlier frame', async () => {
    const frame = { id: 8, name: 'Earlier frame', icon: '🖼', catalog_available: false };
    const onRemove = vi.fn();
    renderWithProviders(<SavedCosmetics cosmetics={{ active_frame: [frame] }} profile={{ active_frame: frame }} onRemove={onRemove} />);
    await userEvent.setup().click(screen.getByRole('button', { name: 'Remove previous selection' }));
    expect(onRemove).toHaveBeenCalledWith('active_frame');
  });
});
