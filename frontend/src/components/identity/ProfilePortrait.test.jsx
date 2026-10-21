import { act, fireEvent, render, screen } from '@testing-library/react';
import { vi } from 'vitest';
import { resolvePortraitFrameImage } from '../../avatar/portraitFrameKit';
import ProfilePortrait from './ProfilePortrait';

vi.mock('../../avatar/portraitFrameKit', async (importOriginal) => ({
  ...await importOriginal(), resolvePortraitFrameImage: vi.fn(() => null),
}));

beforeEach(() => vi.mocked(resolvePortraitFrameImage).mockReset().mockReturnValue(null));

describe('ProfilePortrait', () => {
  it('keeps a readable portrait without an equipped frame', () => {
    const { container } = render(<ProfilePortrait name="Abby" />);
    expect(screen.getByRole('img', { name: "Abby's profile picture" })).toHaveTextContent('A');
    expect(container.querySelector('[data-frame-style]')).toHaveAttribute('data-frame-style', 'plain');
    expect(container.querySelector('svg')).toBeNull();
  });

  it('recovers from a failed photo and allows a replacement URL to load', () => {
    const { container, rerender } = render(<ProfilePortrait name="Abby" avatar="/old-photo.jpg" />);
    fireEvent.error(container.querySelector('img'));
    expect(screen.getByRole('img', { name: "Abby's profile picture" })).toHaveTextContent('A');
    expect(container.querySelector('img')).toBeNull();
    rerender(<ProfilePortrait name="Abby" avatar="/new-photo.jpg" />);
    expect(container.querySelector('img')).toHaveAttribute('src', '/new-photo.jpg');
  });

  it('shows different geometry for the earned frame families', () => {
    const slugs = [
      'frame-bronze', 'frame-silver', 'frame-gold', 'frame-cosmic',
      'frame-barbute', 'frame-robin-hood', 'frame-cross-helm', 'frame-scholar',
      'frame-laurel', 'frame-rune-circle', 'frame-steampunk', 'frame-pixel',
      'hs-prep-2026-frame-high-school-trophy', 'sleep-prep-2026-frame-moonlit',
      'birthday-pack-frame-confetti', 'summer-2026-frame-seashell',
      'year-in-review-pack-frame-chronicle', 'collector-reading-2026-frame-far-horizons',
    ];
    const { container, rerender } = render(<ProfilePortrait name="Abby" />);
    const artwork = slugs.map((slug) => {
      rerender(<ProfilePortrait name="Abby" frame={{ slug, name: slug }} />);
      const frame = container.querySelector('[data-portrait-ornament]');
      expect(frame).toHaveAttribute('aria-hidden', 'true');
      expect(frame).toHaveAttribute('viewBox', '0 0 100 100');
      expect(container.querySelector('[data-frame-style]')).not.toHaveAttribute('data-frame-style', 'custom');
      return frame.querySelector(':scope > g').innerHTML;
    });
    expect(new Set(artwork).size).toBe(slugs.length);
  });

  it('retains a custom frame color without assigning another catalog identity', () => {
    const { container } = render(<ProfilePortrait name="Abby" frame={{ slug: 'custom-frame', name: 'My frame', metadata: { border_color: '#123456' } }} />);
    expect(screen.getByRole('img', { name: "Abby's profile picture with My frame" })).toBeInTheDocument();
    expect(container.firstChild).toHaveAttribute('data-frame-style', 'custom');
    expect(container.firstChild.style.getPropertyValue('--portrait-accent')).toBe('#123456');
  });

  it('recognizes an older compact frame by its exact catalog name', () => {
    const { container } = render(<ProfilePortrait name="Abby" frame={{ name: 'Laurel Wreath Frame' }} />);
    expect(container.firstChild).toHaveAttribute('data-portrait-frame', 'laurel');
  });

  it('preserves an explicitly supplied image label', () => {
    render(<ProfilePortrait name="Abby" avatar="/photo.jpg" imageAlt="Your profile picture" />);
    expect(screen.getByAltText('Your profile picture')).toHaveAttribute('src', '/photo.jpg');
    expect(screen.getByRole('img', { name: 'Your profile picture' })).toBeInTheDocument();
  });

  it('keeps navigation portraits decorative when the adjacent name provides identity', () => {
    const { container } = render(<ProfilePortrait name="Abby" imageAlt="" frame={{ name: 'Laurel Wreath Frame' }} />);
    expect(screen.queryByRole('img')).not.toBeInTheDocument();
    expect(container.firstChild).toHaveAttribute('aria-hidden', 'true');
    expect(container.firstChild).not.toHaveAttribute('aria-label');
  });

  it.each(['frame-chronicle', 'frame-scholar', 'frame-barbute', 'frame-cross-helm', 'frame-laurel'])('keeps the center of %s clear for the face', (slug) => {
    const { container } = render(<ProfilePortrait name="Abby" avatar="/photo.jpg" frame={{ slug }} />);
    const mask = container.querySelector('mask');
    const opening = mask.querySelector('[data-portrait-opening]');
    expect(opening).toHaveAttribute('r', '33');
    expect(opening).toHaveAttribute('cx', '50');
    expect(opening).toHaveAttribute('cy', '50');
    expect(opening).toHaveAttribute('fill', 'black');
    expect(container.querySelector('svg > g')).toHaveAttribute('mask', `url(#${mask.id})`);
    expect(container.querySelector('img')).toHaveAttribute('src', '/photo.jpg');
  });

  it('matches the pixel frame opening to its rounded square portrait', () => {
    const { container } = render(<ProfilePortrait name="Abby" frame={{ slug: 'frame-pixel' }} />);
    const opening = container.querySelector('[data-portrait-opening]');
    expect(opening.tagName).toBe('rect');
    expect(opening).toHaveAttribute('x', '17');
    expect(opening).toHaveAttribute('width', '66');
    expect(opening).toHaveAttribute('height', '66');
  });

  it.each([['xs', '32px'], ['sm', '40px'], ['md', '64px'], ['lg', '96px'], [32, '32px']])('supports the %s portrait size within one fixed box', (size, width) => {
    const { container } = render(<ProfilePortrait name="Abby" size={size} frame={{ slug: 'frame-laurel' }} />);
    expect(container.firstChild.style.getPropertyValue('--portrait-size')).toBe(width);
  });

  it('loads the exact saved frame overlay before replacing its vector fallback', () => {
    vi.mocked(resolvePortraitFrameImage).mockReturnValue({ url: '/synthetic/laurel-40-2x.png', assetId: 'item-frame-laurel', variantId: 'small-40-2x', width: 80, height: 80 });
    const { container } = render(<ProfilePortrait name="Abby" avatar="/photo.jpg" frame={{ slug: 'frame-laurel', name: 'Laurel Wreath Frame' }} size="sm" devicePixelRatio={1.5} />);
    expect(resolvePortraitFrameImage).toHaveBeenCalledWith('frame-laurel', 40, 1.5);
    const overlay = container.querySelector('[data-portrait-overlay="item-frame-laurel"]');
    expect(overlay).toHaveAttribute('src', '/synthetic/laurel-40-2x.png');
    expect(overlay).toHaveAttribute('data-portrait-variant', 'small-40-2x');
    expect(overlay).toHaveAttribute('alt', '');
    expect(overlay).toHaveAttribute('aria-hidden', 'true');
    expect(overlay).toHaveAttribute('hidden');
    expect(container.querySelector('[data-portrait-ornament]')).toBeInTheDocument();
    fireEvent.load(overlay);
    expect(overlay).not.toHaveAttribute('hidden');
    expect(container.querySelector('[data-portrait-ornament]')).toBeNull();
    expect(container.firstChild).toHaveClass('profile-portrait--kit');
    expect(container.querySelector('.profile-portrait__image img')).toHaveAttribute('src', '/photo.jpg');
  });

  it('falls back to the same equipped family when an overlay fails and keeps the initial readable', () => {
    vi.mocked(resolvePortraitFrameImage).mockReturnValue({ url: '/synthetic/steampunk.png', assetId: 'item-frame-steampunk', variantId: 'detail-64-1x' });
    const { container } = render(<ProfilePortrait name="Abby" frame={{ slug: 'frame-steampunk' }} />);
    fireEvent.error(container.querySelector('[data-portrait-overlay]'));
    expect(container.firstChild).toHaveAttribute('data-portrait-frame', 'steampunk');
    expect(container.querySelector('[data-portrait-ornament]')).toBeInTheDocument();
    expect(screen.getByRole('img', { name: "Abby's profile picture" })).toHaveTextContent('A');
    expect(container.querySelector('[data-portrait-overlay]')).toBeNull();
  });

  it('keeps the saved Pixel photo when loading or recovering from the overlay', () => {
    vi.mocked(resolvePortraitFrameImage).mockReturnValue({ url: '/synthetic/pixel.png', assetId: 'item-frame-pixel', variantId: 'small-32-1x' });
    const { container } = render(<ProfilePortrait name="Abby" avatar="/photo.jpg" frame={{ slug: 'frame-pixel' }} size="xs" />);
    const photo = container.querySelector('.profile-portrait__image img');
    const overlay = container.querySelector('[data-portrait-overlay]');
    fireEvent.load(overlay);
    expect(container.querySelector('.profile-portrait__image img')).toBe(photo);
    expect(container.querySelector('[data-portrait-ornament]')).toBeNull();
    fireEvent.error(overlay);
    expect(container.querySelector('.profile-portrait__image img')).toBe(photo);
    expect(photo).toHaveAttribute('src', '/photo.jpg');
    expect(container.querySelector('[data-portrait-ornament]')).toBeInTheDocument();
    expect(container.firstChild).toHaveAttribute('data-portrait-frame', 'pixel');
  });

  it('recovers when a replacement overlay URL arrives without reusing the previous image load', () => {
    vi.mocked(resolvePortraitFrameImage).mockReturnValue({ url: '/synthetic/old.png', assetId: 'item-frame-laurel', variantId: 'detail-64-1x' });
    const { container, rerender } = render(<ProfilePortrait name="Abby" frame={{ slug: 'frame-laurel' }} />);
    fireEvent.load(container.querySelector('[data-portrait-overlay]'));
    vi.mocked(resolvePortraitFrameImage).mockReturnValue({ url: '/synthetic/new.png', assetId: 'item-frame-laurel', variantId: 'detail-64-2x' });
    rerender(<ProfilePortrait name="Abby" frame={{ slug: 'frame-laurel' }} devicePixelRatio={2} />);
    expect(container.querySelector('[data-portrait-overlay]')).toHaveAttribute('hidden');
    fireEvent.error(container.querySelector('[data-portrait-overlay]'));
    vi.mocked(resolvePortraitFrameImage).mockReturnValue({ url: '/synthetic/recovered.png', assetId: 'item-frame-laurel', variantId: 'detail-64-3x' });
    rerender(<ProfilePortrait name="Abby" frame={{ slug: 'frame-laurel' }} devicePixelRatio={3} />);
    expect(container.querySelector('[data-portrait-overlay]')).toHaveAttribute('src', '/synthetic/recovered.png');
  });

  it('uses an exact server catalog icon for older compact frames but never a display name alone', () => {
    const { container, rerender } = render(<ProfilePortrait name="Abby" frame={{ name: 'Laurel Wreath Frame' }} />);
    expect(resolvePortraitFrameImage).toHaveBeenLastCalledWith(undefined, 64, 1);
    rerender(<ProfilePortrait name="Abby" frame={{ name: 'Laurel Wreath Frame', catalog_icon: 'item-frame-laurel' }} />);
    expect(resolvePortraitFrameImage).toHaveBeenLastCalledWith('frame-laurel', 64, 1);
    rerender(<ProfilePortrait name="Abby" frame={{ name: 'An edited display name', catalog_icon: 'item-frame-laurel' }} />);
    expect(container.firstChild).toHaveAttribute('data-portrait-frame', 'laurel');
    rerender(<ProfilePortrait name="Abby" frame={{ slug: 'custom-frame-laurel', catalog_icon: 'item-frame-laurel' }} />);
    expect(resolvePortraitFrameImage).toHaveBeenLastCalledWith('custom-frame-laurel', 64, 1);
  });

  it('reselects density after consecutive display resolution changes', () => {
    const listeners = new Map();
    vi.stubGlobal('devicePixelRatio', 1);
    vi.stubGlobal('matchMedia', (query) => ({
      addEventListener: (_event, callback) => listeners.set(query, callback),
      removeEventListener: () => listeners.delete(query),
    }));
    const { unmount } = render(<ProfilePortrait name="Abby" frame={{ slug: 'frame-laurel' }} />);
    try {
      act(() => { vi.stubGlobal('devicePixelRatio', 2); listeners.get('(resolution: 1dppx)')(); });
      expect(resolvePortraitFrameImage).toHaveBeenLastCalledWith('frame-laurel', 64, 2);
      act(() => { vi.stubGlobal('devicePixelRatio', 3); listeners.get('(resolution: 2dppx)')(); });
      expect(resolvePortraitFrameImage).toHaveBeenLastCalledWith('frame-laurel', 64, 3);
      expect(listeners.has('(resolution: 3dppx)')).toBe(true);
    } finally {
      unmount();
      vi.unstubAllGlobals();
    }
  });
});
