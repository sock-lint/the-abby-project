import { fireEvent, render, screen } from '@testing-library/react';
import ProfilePortrait from './ProfilePortrait';

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

  it.each([['xs', '32px'], ['sm', '40px'], ['md', '64px'], [32, '32px']])('supports the %s portrait size within one fixed box', (size, width) => {
    const { container } = render(<ProfilePortrait name="Abby" size={size} frame={{ slug: 'frame-laurel' }} />);
    expect(container.firstChild.style.getPropertyValue('--portrait-size')).toBe(width);
  });
});
