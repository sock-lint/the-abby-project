import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import CatalogIcon from './CatalogIcon';
import { resolveCatalogIcon } from '../../catalog/sharedCatalogIcons';
import { SpriteCatalogContext } from '../../providers/spriteCatalog.context';
vi.mock('../../catalog/sharedCatalogIcons', () => ({ resolveCatalogIcon: vi.fn() }));

const fallback = { getSpriteMeta: (key) => key === 'food-meat' ? { url: '/legacy/meat.png', frames: 1 } : null };
function view(assetId = 'item-meat', extra = {}) {
  return <SpriteCatalogContext.Provider value={fallback}><CatalogIcon assetId={assetId} spriteKey="food-meat" icon="🍗" alt="Meat" {...extra} /></SpriteCatalogContext.Provider>;
}
describe('CatalogIcon', () => {
  beforeEach(() => resolveCatalogIcon.mockImplementation((id) => id ? { url: `/private/${id}.png`, label: 'Meat' } : null));
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
});
