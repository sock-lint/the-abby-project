import { describe, it, expect, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import RpgSprite from './RpgSprite';
import { SpriteCatalogProvider } from '../../providers/SpriteCatalogProvider';

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
  });

  it('renders a static sprite as an <img>', () => {
    renderWithCatalog(
      <RpgSprite spriteKey="dragon" icon="🐉" size={32} alt="dragon" />,
      { dragon: { url: 'https://s/dragon.png', frames: 1, fps: 0, w: 32, h: 32, layout: 'horizontal' } }
    );
    const img = screen.getByAltText('dragon');
    expect(img.tagName).toBe('IMG');
    expect(img.src).toBe('https://s/dragon.png');
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
