import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import CardStyleArtwork from './CardStyleArtwork';
import { resolvePedestalImage } from '../../pedestal/pedestalRelease';

vi.mock('../../pedestal/pedestalRelease', () => ({ resolvePedestalImage: vi.fn() }));
beforeEach(() => { resolvePedestalImage.mockReset(); resolvePedestalImage.mockReturnValue(null); });

describe('CardStyleArtwork', () => {
  it.each(['card-front-nature', 'card-front-light'])('renders the complete decorative %s canvas', (assetId) => {
    resolvePedestalImage.mockReturnValue({ assetId, variantId: 'web', url: `/synthetic/${assetId}.png`, width: 512, height: 512 });
    const { container } = render(<CardStyleArtwork frame={{ metadata: { card_asset_id: assetId } }} />);
    expect(container.querySelector('img')).toHaveAttribute('width', '512');
    expect(container.querySelector('img')).toHaveAttribute('height', '512');
    expect(container.querySelector('img')).toHaveAttribute('alt', '');
    expect(screen.queryByRole('img')).toBeNull();
    expect(container.querySelector('button, [tabindex]')).toBeNull();
  });

  it('never infers a style from frame names or unsupported artwork metadata', () => {
    const { container, rerender } = render(<CardStyleArtwork frame={{ name: 'Nature Frame', rarity: 'legendary' }} />);
    expect(container).toBeEmptyDOMElement();
    rerender(<CardStyleArtwork frame={{ metadata: { card_asset_id: 'frame-gold' } }} />);
    expect(container).toBeEmptyDOMElement();
    expect(resolvePedestalImage).not.toHaveBeenCalled();
  });

  it('keeps unavailable and failed decorative artwork silent', () => {
    const frame = { metadata: { card_asset_id: 'card-front-nature' } };
    const { container, rerender } = render(<CardStyleArtwork frame={frame} />);
    expect(container.querySelector('[data-image-state="unavailable"]')).toHaveAttribute('aria-hidden', 'true');
    expect(screen.queryByText('Artwork unavailable')).toBeNull();
    resolvePedestalImage.mockReturnValue({ assetId: 'card-front-nature', variantId: 'web', url: '/synthetic/nature.png', width: 512, height: 512 });
    rerender(<CardStyleArtwork frame={frame} />);
    fireEvent.error(container.querySelector('img'));
    expect(container.querySelector('[data-image-state="error"]')).not.toBeNull();
    expect(screen.queryByRole('img')).toBeNull();
    expect(screen.queryByText('Artwork unavailable')).toBeNull();
  });
});
