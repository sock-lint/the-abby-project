import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import ArtworkImage from './ArtworkImage';
import { resolveArtworkImage } from '../../catalog/sharedArtwork';

vi.mock('../../catalog/sharedArtwork', () => ({ resolveArtworkImage: vi.fn() }));
beforeEach(() => resolveArtworkImage.mockReset());

describe('ArtworkImage', () => {
  it('keeps artwork decorative at the requested size without replacing the adjacent name', () => {
    resolveArtworkImage.mockReturnValue({ url: '/synthetic/art.png' });
    const { container } = render(<button>Custom name<ArtworkImage assetId="exact-art" size={40} fallback="🦉✨" /></button>);
    const image = container.querySelector('img');
    expect(image).toHaveAttribute('src', '/synthetic/art.png');
    expect(image).toHaveAttribute('alt', '');
    expect(image).toHaveAttribute('aria-hidden', 'true');
    expect(image).toHaveStyle({ width: '40px', height: '40px', objectFit: 'contain', imageRendering: 'auto' });
    expect(screen.getByRole('button', { name: 'Custom name' })).toBeInTheDocument();
    expect(screen.queryByRole('img')).toBeNull();
  });

  it('preserves the complete authored glyph when identity or the installed release is unavailable', () => {
    resolveArtworkImage.mockReturnValue(null);
    const { container } = render(<ArtworkImage assetId={null} fallback="🦉✨" />);
    expect(container.querySelector('img')).toBeNull();
    expect(screen.getByText('🦉✨')).toBeInTheDocument();
  });

  it('keeps a failed URL on its fallback across rerenders and retries a fresh catalog URL', () => {
    resolveArtworkImage.mockReturnValue({ url: '/synthetic/first.png' });
    const { container, rerender } = render(<ArtworkImage assetId="exact-art" fallback="🦉✨" />);
    fireEvent.error(container.querySelector('img'));
    expect(screen.getByText('🦉✨')).toBeInTheDocument();
    rerender(<ArtworkImage assetId="exact-art" fallback="🦉✨" />);
    expect(container.querySelector('img')).toBeNull();
    resolveArtworkImage.mockReturnValue({ url: '/synthetic/replacement.png' });
    rerender(<ArtworkImage assetId="exact-art" fallback="🦉✨" size="50cqw" />);
    expect(container.querySelector('img')).toHaveAttribute('src', '/synthetic/replacement.png');
    expect(container.querySelector('img')).toHaveStyle({ width: '50cqw' });
  });
});
