import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import BadgeArtwork from './BadgeArtwork';
import { resolvePedestalImage } from '../../pedestal/pedestalRelease';

vi.mock('../../pedestal/pedestalRelease', () => ({ resolvePedestalImage: vi.fn() }));
beforeEach(() => resolvePedestalImage.mockReturnValue(null));

describe('BadgeArtwork', () => {
  const badge = { name: 'Night Owl', icon: '🦉', rarity: 'rare' };

  it('keeps collection artwork quiet for earned and future badges', () => {
    const { container, rerender } = render(<BadgeArtwork badge={badge} earned />);
    expect(screen.getByText('🦉')).toBeInTheDocument();
    expect(container.querySelector('[data-pedestal-image]')).toBeNull();
    rerender(<BadgeArtwork badge={badge} variant="featured" earned={false} />);
    expect(screen.getByText('🦉')).toBeInTheDocument();
    expect(container.querySelector('[data-pedestal-image]')).toBeNull();
  });

  it('retains the real badge icon when its featured frame is missing or fails', () => {
    const { container, rerender } = render(<BadgeArtwork badge={badge} earned variant="featured" />);
    expect(container.querySelector('[data-pedestal-image="frame-gold"]')).toHaveAttribute('data-image-state', 'unavailable');
    expect(screen.getByText('🦉')).toBeInTheDocument();
    resolvePedestalImage.mockReturnValue({ assetId: 'frame-gold', variantId: 'web', url: '/private/synthetic-frame.png', width: 512, height: 512 });
    rerender(<BadgeArtwork badge={badge} earned variant="featured" />);
    fireEvent.error(container.querySelector('img'));
    expect(container.querySelector('[data-pedestal-image="frame-gold"]')).toHaveAttribute('data-image-state', 'error');
    expect(screen.getByText('🦉')).toBeInTheDocument();
    expect(screen.queryByRole('img')).toBeNull();
    expect(container.querySelector('button, [tabindex]')).toBeNull();
  });

  it('keeps the medal fallback when a badge has no supplied icon', () => {
    render(<BadgeArtwork badge={{ name: 'An earned achievement' }} earned variant="featured" />);
    expect(screen.getByText('🏅')).toBeInTheDocument();
  });

  it('preserves every supplied emoji in a multi-emoji badge icon', () => {
    render(<BadgeArtwork badge={{ name: 'A thoughtful achievement', icon: '🦉✨' }} earned variant="featured" />);
    expect(screen.getByText('🦉✨')).toBeInTheDocument();
  });
});
