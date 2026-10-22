import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import RpgSprite from './RpgSprite';
import { SpriteCatalogProvider } from '../../providers/SpriteCatalogProvider';
import { SpriteCatalogContext } from '../../providers/spriteCatalog.context';
import presentation from '../../storybook/presentation.json';
import { getLicensedRpgSprite, resolveLicensedRpgSprite } from '../../storybook/licensedRpgSprites';
import { resolveElementalPortrait } from '../../companion/sharedElementalPortraits';

vi.mock('../../companion/sharedElementalPortraits', () => ({ resolveElementalPortrait: vi.fn(() => null) }));

vi.mock('../../storybook/licensedRpgSprites', async () => {
  const actual = await vi.importActual('../../storybook/licensedRpgSprites');
  return { ...actual, getLicensedRpgSprite: vi.fn(() => null) };
});

function useSyntheticLicensedPortraits() {
  const manifest = {
    schema_version: presentation.schema_version,
    companion: { id: presentation.companion.id, art_key: 'chick', temporary: false, portrait: 'chick.png' },
  };
  const art = (name) => ({ 'chick.png': '/assets/synthetic-chick.png', 'bird.png': '/assets/synthetic-bird.png' })[name];
  getLicensedRpgSprite.mockImplementation((key) => resolveLicensedRpgSprite(key, manifest, art));
}

// Seed the catalog via localStorage so the provider resolves immediately
// without network.
function seedCatalog(sprites) {
  const catalog = { etag: 'test', sprites };
  localStorage.setItem('spriteCatalog', JSON.stringify(catalog));
  localStorage.setItem('spriteCatalogEtag', 'test');
}

function renderWithCatalog(node, sprites) {
  seedCatalog(sprites);
  return render(<SpriteCatalogProvider>{node}</SpriteCatalogProvider>);
}

describe('RpgSprite', () => {
  beforeEach(() => {
    localStorage.clear();
    getLicensedRpgSprite.mockReset().mockReturnValue(null);
    resolveElementalPortrait.mockReset().mockReturnValue(null);
  });

  it.each(['fire', 'ice'])('uses exact %s stage images at every size, with dimming separate from appearance', (potionSlug) => {
    resolveElementalPortrait.mockImplementation((key, potion) => ({ url: `/elemental/${key}-${potion}.png`, frames: 1 }));
    const keys = ['cute-chick', 'cute-chick-fledgling', 'cute-chick-mount', 'meshtint-wolf', 'meshtint-wolf-middle', 'meshtint-wolf-mount',
      'meshtint-dragon', 'meshtint-dragon-middle', 'meshtint-dragon-mount', 'meshtint-mushroom', 'meshtint-mushroom-middle', 'meshtint-mushroom-mount'];
    const { rerender } = render(<RpgSprite spriteKey={keys[0]} potionSlug={potionSlug} alt="Elemental pet" />);
    for (const spriteKey of keys) {
      for (const size of [24, 32, 64, 96, 128, 256]) {
        rerender(<RpgSprite spriteKey={spriteKey} fallbackSpriteKey="cute-chick" potionSlug={potionSlug} size={size} dim="stale" alt="Elemental pet" />);
        expect(screen.getByRole('img', { name: 'Elemental pet' })).toHaveAttribute('src', `/elemental/${spriteKey}-${potionSlug}.png`);
        expect(screen.getByRole('img', { name: 'Elemental pet' })).toHaveStyle({ width: `${size}px`, filter: 'grayscale(0.5) opacity(0.7)' });
        expect(resolveElementalPortrait).toHaveBeenLastCalledWith(spriteKey, potionSlug);
      }
    }
    expect(getLicensedRpgSprite).not.toHaveBeenCalled();
  });

  it('retains the exact identity as a labelled icon after a failed image instead of trying a different stage/species', () => {
    resolveElementalPortrait.mockImplementation((key, potion) => ({ url: `/elemental/${key}-${potion}.png`, frames: 1 }));
    const view = (key, potion) => <RpgSprite spriteKey={key} fallbackSpriteKey="meshtint-wolf" potionSlug={potion} icon="🐾" dim="bored" alt="Fire Fledgling" />;
    const { rerender } = renderWithCatalog(view('cute-chick-fledgling', 'fire'), { 'cute-chick-fledgling': { url: '/base-fledgling.png', frames: 1 } });
    fireEvent.error(screen.getByRole('img', { name: 'Fire Fledgling' }));
    expect(screen.getByRole('img', { name: 'Fire Fledgling' }).tagName).toBe('SPAN');
    expect(screen.getByRole('img', { name: 'Fire Fledgling' })).toHaveTextContent('🐾');
    expect(screen.getByRole('img', { name: 'Fire Fledgling' })).toHaveStyle({ filter: 'grayscale(0.25) opacity(0.85)' });
    rerender(<SpriteCatalogProvider>{view('cute-chick-mount', 'ice')}</SpriteCatalogProvider>);
    expect(screen.getByRole('img', { name: 'Fire Fledgling' })).toHaveAttribute('src', '/elemental/cute-chick-mount-ice.png');
  });

  it.each(['cute-chick', 'cute-chick-fledgling', 'cute-chick-mount', 'meshtint-wolf', 'meshtint-wolf-middle', 'meshtint-wolf-mount',
    'meshtint-dragon', 'meshtint-dragon-middle', 'meshtint-dragon-mount', 'meshtint-mushroom', 'meshtint-mushroom-middle', 'meshtint-mushroom-mount'])(
    'keeps %s elemental artwork unavailable instead of recoloring its Base portrait', (spriteKey) => {
      useSyntheticLicensedPortraits();
      renderWithCatalog(<RpgSprite spriteKey={spriteKey} icon="🐾" alt="Fire companion" potionSlug="fire" dim="stale" />,
        { [spriteKey]: { url: '/assets/base-only.png', frames: 1 } });
      const portrait = screen.getByRole('img', { name: 'Fire companion' });
      expect(portrait.tagName).toBe('SPAN');
      expect(portrait).toHaveTextContent('🐾');
      expect(portrait).toHaveStyle({ filter: 'grayscale(0.5) opacity(0.7)' });
    });

  it.each([
    ['cute-chick', '/assets/synthetic-chick.png'],
    ['cute-chick-mount', '/assets/synthetic-bird.png'],
  ])('renders the staged portrait for %s without a runtime sprite', (spriteKey, url) => {
    useSyntheticLicensedPortraits();
    render(<RpgSprite spriteKey={spriteKey} icon="🐥" alt="Chick" potionSlug="base" dim="stale" />);
    const portrait = screen.getByRole('img', { name: 'Chick' });
    expect(portrait).toHaveAttribute('src', url);
    expect(portrait).toHaveStyle({ objectFit: 'contain', imageRendering: 'auto', filter: 'grayscale(0.5) opacity(0.7)' });
  });

  it('recovers from failed licensed art through runtime and base-species portraits', () => {
    useSyntheticLicensedPortraits();
    renderWithCatalog(<RpgSprite spriteKey="cute-chick-mount" fallbackSpriteKey="cute-chick" icon="🐥" alt="Chick mount" />,
      { 'cute-chick-mount': { url: 'https://s/runtime-bird.png', frames: 1 }, 'cute-chick': { url: 'https://s/runtime-chick.png', frames: 1 } });
    for (const url of ['/assets/synthetic-bird.png', 'https://s/runtime-bird.png', '/assets/synthetic-chick.png', 'https://s/runtime-chick.png']) {
      const portrait = screen.getByRole('img', { name: 'Chick mount' });
      expect(portrait).toHaveAttribute('src', url);
      fireEvent.error(portrait);
    }
    const fallback = screen.getByRole('img', { name: 'Chick mount' });
    expect(fallback.tagName).toBe('SPAN');
    expect(fallback).toHaveTextContent('🐥');
  });

  it('uses the runtime Chick catalog when licensed assets are absent', () => {
    renderWithCatalog(<RpgSprite spriteKey="cute-chick" icon="🐥" alt="Chick" />,
      { 'cute-chick': { url: 'https://s/runtime-chick.png', frames: 1 } });
    expect(screen.getByRole('img', { name: 'Chick' })).toHaveAttribute('src', 'https://s/runtime-chick.png');
  });

  it('keeps another species on its own runtime artwork in a licensed build', () => {
    useSyntheticLicensedPortraits();
    renderWithCatalog(<RpgSprite spriteKey="wolf" icon="🐺" alt="Wolf" />,
      { wolf: { url: 'https://s/wolf.png', frames: 1 } });
    expect(screen.getByRole('img', { name: 'Wolf' })).toHaveAttribute('src', 'https://s/wolf.png');
  });

  it('renders a static sprite as an <img>', () => {
    renderWithCatalog(
      <RpgSprite spriteKey="dragon" icon="🐉" size={32} alt="dragon" />,
      { dragon: { url: 'https://s/dragon.png', frames: 1, fps: 0, w: 32, h: 32, layout: 'horizontal' } }
    );
    const img = screen.getByAltText('dragon');
    expect(img.tagName).toBe('IMG');
    expect(img.src).toBe('https://s/dragon.png');
    expect(img).toHaveStyle({ imageRendering: 'auto', objectFit: 'contain' });
  });

  it('supports an explicit crisp rendering mode for pixel artwork', () => {
    renderWithCatalog(<RpgSprite spriteKey="dragon" alt="dragon" rendering="pixelated" />,
      { dragon: { url: 'https://s/dragon.png', frames: 1 } });
    expect(screen.getByAltText('dragon')).toHaveStyle({ imageRendering: 'pixelated' });
  });

  it('tries the base species when the primary portrait fails, then keeps a labelled icon', () => {
    renderWithCatalog(<RpgSprite spriteKey="fox-mount" fallbackSpriteKey="fox" icon="🦊" alt="Fox mount" dim="bored" />,
      { 'fox-mount': { url: 'https://s/mount.png', frames: 1 }, fox: { url: 'https://s/fox.png', frames: 1 } });
    fireEvent.error(screen.getByRole('img', { name: 'Fox mount' }));
    expect(screen.getByRole('img', { name: 'Fox mount' })).toHaveAttribute('src', 'https://s/fox.png');
    fireEvent.error(screen.getByRole('img', { name: 'Fox mount' }));
    const fallback = screen.getByRole('img', { name: 'Fox mount' });
    expect(fallback.tagName).toBe('SPAN');
    expect(fallback).toHaveTextContent('🦊');
    expect(fallback).toHaveAttribute('data-dim', 'bored');
    expect(fallback).toHaveStyle({ filter: 'grayscale(0.25) opacity(0.85)' });
  });

  it('recovers from a failure when the catalog supplies a fresh URL', () => {
    const sprite = (url) => ({ getSpriteMeta: () => ({ url, frames: 1 }) });
    const ui = (url) => <SpriteCatalogContext.Provider value={sprite(url)}><RpgSprite spriteKey="bird" icon="🐦" alt="Bird" /></SpriteCatalogContext.Provider>;
    const { rerender } = render(ui('https://s/old.png'));
    fireEvent.error(screen.getByRole('img', { name: 'Bird' }));
    expect(screen.getByRole('img', { name: 'Bird' }).tagName).toBe('SPAN');
    rerender(ui('https://s/new.png'));
    expect(screen.getByRole('img', { name: 'Bird' })).toHaveAttribute('src', 'https://s/new.png');
  });

  it('falls back accessibly when an animated strip fails to load', () => {
    const { container } = renderWithCatalog(<RpgSprite spriteKey="flame" icon="🔥" alt="Flame" />,
      { flame: { url: 'https://s/flame.png', frames: 4, fps: 6 } });
    fireEvent.error(container.querySelector('img'));
    expect(screen.getByRole('img', { name: 'Flame' })).toHaveTextContent('🔥');
    expect(container.querySelector('img')).toBeNull();
  });

  it.each([1, 4])('ignores an old image error after the URL changes (%s frames)', (frames) => {
    const ui = (url) => <SpriteCatalogContext.Provider value={{ getSpriteMeta: () => ({ url, frames, fps: 6 }) }}><RpgSprite spriteKey="bird" icon="🐦" alt="Bird" /></SpriteCatalogContext.Provider>;
    const { container, rerender } = render(ui('https://s/old.png'));
    const oldImage = container.querySelector('img');
    rerender(ui('https://s/new.png'));
    fireEvent.error(oldImage);
    expect(container.querySelector('img')).toHaveAttribute('src', 'https://s/new.png');
    expect(screen.getByRole('img', { name: 'Bird' })).not.toHaveTextContent('🐦');
  });

  it('renders an animated sprite as a span with canonical step animation', () => {
    // Canonical sprite-sheet animation technique: `steps(N)` (= jump-end)
    // holds each of N frames for 1/N of the duration and "jumps" at t=1
    // to the off-sheet position -N*size, which is never visible because
    // the animation loops back to 0 instantly. The previous technique
    // (`steps(N, jump-none)` with endX = -(N-1)*size) held the first N-1
    // frames for 1/(N-1) each and flashed frame N-1 only at the loop
    // boundary — users saw the last pose as a brief ghost, easily
    // mistaken for a bleed or rendering artifact.
    renderWithCatalog(
      <RpgSprite spriteKey="flame" icon="🔥" size={32} alt="flame" />,
      { flame: { url: 'https://s/flame.png', frames: 4, fps: 6, w: 16, h: 16, layout: 'horizontal' } }
    );
    const el = screen.getByLabelText('flame');
    expect(el.tagName).toBe('SPAN');
    const style = el.getAttribute('style') || '';
    expect(style).toContain('animation: sprite-cycle');
    // duration = frames/fps = 4/6 ≈ 0.667s — matches any 0.6x string
    expect(style).toMatch(/0\.6\d*s/);
    // steps(4) is the default jump-end behavior. Must NOT be jump-none.
    expect(style).toContain('steps(4)');
    expect(style).not.toContain('jump-none');
    // With size=32 and frames=4: end-x = -4 × 32 = -128px (off-sheet,
    // never visible thanks to the instant loop at t=1).
    expect(style).toContain('--sprite-end-x: -128px');
  });

  it('emoji-fallbacks for unknown slug', () => {
    renderWithCatalog(<RpgSprite spriteKey="missing" icon="✨" size={32} />, {});
    expect(screen.getByText('✨')).toBeInTheDocument();
  });

  it('falls through to fallbackSpriteKey when primary slug is missing', () => {
    // Mount-tier sprites are named `{species}-mount`; for species without
    // drawn evolved forms the frontend passes the base sprite key as
    // fallbackSpriteKey so UserMount rows still render a pixel-art tile.
    renderWithCatalog(
      <RpgSprite
        spriteKey="fox-mount"
        fallbackSpriteKey="fox"
        icon="🦊"
        size={32}
        alt="fox mount"
      />,
      { fox: { url: 'https://s/fox.png', frames: 1, fps: 0, w: 32, h: 32, layout: 'horizontal' } }
    );
    const img = screen.getByAltText('fox mount');
    expect(img.tagName).toBe('IMG');
    expect(img.src).toBe('https://s/fox.png');
  });

  it('prefers primary spriteKey over fallback when both exist', () => {
    renderWithCatalog(
      <RpgSprite
        spriteKey="wolf-mount"
        fallbackSpriteKey="wolf"
        icon="🐺"
        size={32}
        alt="wolf mount"
      />,
      {
        wolf: { url: 'https://s/wolf.png', frames: 1, fps: 0, w: 32, h: 32, layout: 'horizontal' },
        'wolf-mount': { url: 'https://s/wolf-mount.png', frames: 4, fps: 4, w: 32, h: 32, layout: 'horizontal' },
      }
    );
    const el = screen.getByLabelText('wolf mount');
    const style = el.getAttribute('style') || '';
    expect(style).toContain('wolf-mount.png');
    expect(style).not.toContain('wolf.png"');
  });

  // Potion-based recolor — one base sprite covers N potion variants
  // without a dedicated asset per (species, potion) combo.
  it('applies a hue-rotate filter when potionSlug is set (static)', () => {
    renderWithCatalog(
      <RpgSprite spriteKey="wolf" icon="🐺" size={32} alt="shadow wolf" potionSlug="shadow" />,
      { wolf: { url: 'https://s/wolf.png', frames: 1, fps: 0, w: 32, h: 32, layout: 'horizontal' } }
    );
    const img = screen.getByAltText('shadow wolf');
    const style = img.getAttribute('style') || '';
    expect(style).toMatch(/filter:\s*hue-rotate\(260deg\)/);
  });

  it('applies a hue-rotate filter when potionSlug is set (animated)', () => {
    renderWithCatalog(
      <RpgSprite spriteKey="dragon" icon="🐉" size={32} alt="fire dragon" potionSlug="fire" />,
      { dragon: { url: 'https://s/dragon.png', frames: 4, fps: 4, w: 32, h: 32, layout: 'horizontal' } }
    );
    const el = screen.getByLabelText('fire dragon');
    const style = el.getAttribute('style') || '';
    expect(style).toMatch(/filter:\s*hue-rotate\(330deg\)/);
  });

  it('applies no filter when potionSlug is unset or is base', () => {
    renderWithCatalog(
      <RpgSprite spriteKey="wolf" icon="🐺" size={32} alt="natural wolf" potionSlug="base" />,
      { wolf: { url: 'https://s/wolf.png', frames: 1, fps: 0, w: 32, h: 32, layout: 'horizontal' } }
    );
    const img = screen.getByAltText('natural wolf');
    const style = img.getAttribute('style') || '';
    expect(style).not.toMatch(/filter:\s*hue-rotate/);
  });
});
