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

  it('renders an animated sprite as a span with computed animation style', () => {
    renderWithCatalog(
      <RpgSprite spriteKey="flame" icon="🔥" size={32} alt="flame" />,
      { flame: { url: 'https://s/flame.png', frames: 4, fps: 6, w: 16, h: 16, layout: 'horizontal' } }
    );
    const el = screen.getByLabelText('flame');
    expect(el.tagName).toBe('SPAN');
    const style = el.getAttribute('style') || '';
    expect(style).toContain('animation: sprite-cycle-4');
    // duration = frames/fps = 4/6 ≈ 0.667s — matches any 0.6x string
    expect(style).toMatch(/0\.6\d*s/);
    expect(style).toContain('steps(4)');
  });

  it('emoji-fallbacks for unknown slug', () => {
    renderWithCatalog(<RpgSprite spriteKey="missing" icon="✨" size={32} />, {});
    expect(screen.getByText('✨')).toBeInTheDocument();
  });
});
