import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import RewardItem from './RewardItem';
import { resolveCatalogIcon } from '../../catalog/sharedCatalogIcons';
import { SpriteCatalogContext } from '../../providers/spriteCatalog.context';

vi.mock('../../catalog/sharedCatalogIcons', () => ({ resolveCatalogIcon: vi.fn() }));

describe('RewardItem', () => {
  beforeEach(() => resolveCatalogIcon.mockReturnValue(null));

  it('preserves a promised item identity through missing artwork and sprite fallback', () => {
    resolveCatalogIcon.mockReturnValue({ url: '/synthetic/reward.png' });
    render(<SpriteCatalogContext.Provider value={{ getSpriteMeta: () => ({ url: '/synthetic/sprite.png', frames: 1 }) }}>
      <RewardItem item={{ item_name: 'Reward frame', item_catalog_icon: 'frame-reward', item_sprite_key: 'frame', item_icon: '🖼️', item_rarity: 'rare', quantity: 2 }} />
    </SpriteCatalogContext.Provider>);
    fireEvent.error(screen.getByAltText(''));
    expect(screen.getByRole('img', { name: 'frame' })).toHaveAttribute('src', '/synthetic/sprite.png');
    fireEvent.error(screen.getByRole('img', { name: 'frame' }));
    expect(screen.getByText('Reward frame ×2')).toBeInTheDocument();
    expect(screen.getByText('rare')).toBeInTheDocument();
    expect(screen.getByText('🖼️')).toBeInTheDocument();
  });

  it('keeps a historical receipt without recorded rarity readable without inventing a tier', () => {
    render(<RewardItem item={{ item_name: 'Earlier reward', quantity: 1 }} />);
    expect(screen.getByText('Earlier reward ×1')).toBeInTheDocument();
    expect(screen.queryByText('common')).toBeNull();
  });

  it('shows a zero-coin conversion and the supplied effect from an expedition receipt', () => {
    render(<RewardItem item={{ name: 'Saved frame', rarity: 'epic', quantity: 1, salvaged_to_coins: 0, effect_summary: 'A frame for your profile.' }} showQuantity={false} />);
    expect(screen.getByText('Saved frame')).toBeInTheDocument();
    expect(screen.getByText('epic')).toBeInTheDocument();
    expect(screen.getByText('Duplicate exchanged for 0 coins')).toBeInTheDocument();
    expect(screen.getByText('A frame for your profile.')).toBeInTheDocument();
  });
});
