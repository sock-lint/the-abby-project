import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import CatalogIcon from './CatalogIcon';
import { resolveCatalogIcon } from '../../catalog/sharedCatalogIcons';
import { resolveArtworkImage } from '../../catalog/sharedArtwork';
import { SpriteCatalogContext } from '../../providers/spriteCatalog.context';
import { resolveElementalCatalogIcon } from '../../companion/sharedElementalPortraits';
vi.mock('../../companion/sharedElementalPortraits', () => ({ resolveElementalCatalogIcon: vi.fn(() => null) }));
vi.mock('../../catalog/sharedCatalogIcons', () => ({ resolveCatalogIcon: vi.fn() }));
vi.mock('../../catalog/sharedArtwork', () => ({ resolveArtworkImage: vi.fn() }));

const fallback = { getSpriteMeta: (key) => key === 'food-meat' ? { url: '/legacy/meat.png', frames: 1 } : null };
function view(assetId = 'item-meat', extra = {}) {
  return <SpriteCatalogContext.Provider value={fallback}><CatalogIcon assetId={assetId} spriteKey="food-meat" icon="🍗" alt="Meat" {...extra} /></SpriteCatalogContext.Provider>;
}
describe('CatalogIcon', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    resolveArtworkImage.mockReturnValue(null);
    resolveElementalCatalogIcon.mockReturnValue(null);
    resolveCatalogIcon.mockImplementation((id) => ['item-meat', 'item-chicken-leg'].includes(id) ? { url: `/private/${id}.png`, label: 'Meat' } : null);
  });
  it.each([32, 40, 64, 96])('renders a smooth, static contained PNG at %s CSS pixels', (size) => {
    render(view('item-meat', { size }));
    const image = screen.getByRole('img', { name: 'Meat' });
    expect(image).toHaveAttribute('src', '/private/item-meat.png');
    expect(image).toHaveStyle({ width: `${size}px`, height: `${size}px`, objectFit: 'contain', imageRendering: 'auto' });
    expect(image.style.animation).toBe('');
  });
  it('tries the existing sprite then emoji when the private image fails', () => {
    render(view());
    fireEvent.error(screen.getByRole('img', { name: 'Meat' }));
    expect(screen.getByRole('img', { name: 'Meat' })).toHaveAttribute('src', '/legacy/meat.png');
    fireEvent.error(screen.getByRole('img', { name: 'Meat' }));
    expect(screen.getByRole('img', { name: 'Meat' })).toHaveTextContent('🍗');
  });
  it('binds failures to URLs and tries a different identity without remounting', () => {
    const { rerender } = render(view());
    fireEvent.error(screen.getByRole('img', { name: 'Meat' }));
    rerender(view('item-chicken-leg'));
    expect(screen.getByRole('img', { name: 'Meat' })).toHaveAttribute('src', '/private/item-chicken-leg.png');
  });
  it('uses fallbacks when identity is absent and permits decorative PNG alt text', () => {
    const { rerender } = render(view(null));
    expect(screen.getByRole('img', { name: 'Meat' })).toHaveAttribute('src', '/legacy/meat.png');
    rerender(view('item-meat', { alt: '' }));
    expect(screen.getByAltText('')).toHaveAttribute('src', '/private/item-meat.png');
  });
  it.each(['item-accessory-crown', 'challenge-birthday-week'])('uses completion artwork for the new %s identity and retains its fallback', (assetId) => {
    resolveArtworkImage.mockImplementation((id) => id === assetId ? { url: `/private/completion/${id}.png` } : null);
    render(view(assetId, { alt: 'New catalog art', icon: '🎁', spriteKey: 'unavailable-sprite' }));
    const image = screen.getByRole('img', { name: 'New catalog art' });
    expect(image).toHaveAttribute('src', `/private/completion/${assetId}.png`);
    expect(resolveArtworkImage).toHaveBeenCalledWith(assetId);
    fireEvent.error(image);
    expect(screen.getByRole('img', { name: 'New catalog art' })).toHaveTextContent('🎁');
  });
  it.each(['item-fire-potion', 'item-ice-potion', 'challenge-ember-nest', 'challenge-frost-nest', 'challenge-ember-trail', 'challenge-frost-trail'])(
    'uses the exact elemental %s image and keeps an accessible failure fallback', (assetId) => {
      resolveElementalCatalogIcon.mockImplementation((id) => id === assetId ? { url: `/elemental/${id}.png` } : null);
      render(view(assetId, { alt: 'Elemental catalog art', icon: '🔥', spriteKey: 'missing-image' }));
      const image = screen.getByRole('img', { name: 'Elemental catalog art' });
      expect(image).toHaveAttribute('src', `/elemental/${assetId}.png`);
      fireEvent.error(image);
      expect(screen.getByRole('img', { name: 'Elemental catalog art' })).toHaveTextContent('🔥');
    },
  );
});
