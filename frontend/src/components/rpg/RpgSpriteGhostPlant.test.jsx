import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import RpgSprite from './RpgSprite';
import { SpriteCatalogContext } from '../../providers/spriteCatalog.context';
import { GHOST_PLANT_SPECIES, stagedGhostPlantFixture } from '../../test/ghostPlantReleaseFixture';

const appearances = GHOST_PLANT_SPECIES.flatMap((species) => ['fire', 'ice'].flatMap((potion) =>
  ['', '-middle', '-mount'].map((suffix) => [`${species}${suffix}`, potion])));

describe('explicit synthetic Ghost/Potted Plant portrait delivery', () => {
  it.each(appearances)('keeps %s %s on its exact image or a readable glyph after missing/failed artwork', (spriteKey, potion) => {
    const staged = stagedGhostPlantFixture();
    const getSpriteMeta = vi.fn(() => ({ url: '/synthetic-base-portrait.png', frames: 1 }));
    const view = (elemental) => <SpriteCatalogContext.Provider value={{ getSpriteMeta }}>
      <RpgSprite spriteKey={spriteKey} potionSlug={potion} alt="Exact elemental pet" icon="🐾" dim="stale" elemental={elemental} />
    </SpriteCatalogContext.Provider>;
    const { rerender } = render(view(staged));
    const image = screen.getByRole('img', { name: 'Exact elemental pet' });
    expect(image).toHaveAttribute('src', expect.stringContaining('/synthetic-ghost-plant/objects/'));
    expect(image).toHaveStyle({ filter: 'grayscale(0.5) opacity(0.7)', imageRendering: 'auto' });
    fireEvent.error(image);
    expect(screen.getByRole('img', { name: 'Exact elemental pet' }).tagName).toBe('SPAN');
    expect(screen.getByRole('img', { name: 'Exact elemental pet' })).toHaveTextContent('🐾');
    expect(screen.getByRole('img', { name: 'Exact elemental pet' })).toHaveStyle({ filter: 'grayscale(0.5) opacity(0.7)' });
    rerender(view(null));
    expect(screen.getByRole('img', { name: 'Exact elemental pet' }).tagName).toBe('SPAN');
    expect(screen.getByRole('img', { name: 'Exact elemental pet' })).toHaveTextContent('🐾');
    expect(getSpriteMeta).not.toHaveBeenCalled();
    expect(document.querySelector('img[src="/synthetic-base-portrait.png"]')).toBeNull();
  });
});
