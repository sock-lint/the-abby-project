import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import PedestalImage from './PedestalImage';
import PedestalFrame from './PedestalFrame';
import { resolvePedestalImage } from './pedestalRelease';

vi.mock('./pedestalRelease', () => ({ resolvePedestalImage: vi.fn() }));

const image = { url: '/private/synthetic-card.png', width: 512, height: 512, assetId: 'card-front-nature', variantId: 'web' };

beforeEach(() => resolvePedestalImage.mockReturnValue(image));

describe('Private proportional PNG presentation', () => {
  it('keeps the full canvas dimensions and loads lazily before showing the PNG', () => {
    const { container } = render(<PedestalImage assetId="card-front-nature" alt="Nature card artwork" />);
    const canvas = container.querySelector('img');
    expect(canvas).toHaveAttribute('width', '512');
    expect(canvas).toHaveAttribute('height', '512');
    expect(canvas).toHaveAttribute('loading', 'lazy');
    expect(canvas).toHaveAttribute('decoding', 'async');
    expect(container.firstChild).toHaveAttribute('data-image-state', 'loading');
    fireEvent.load(canvas);
    expect(container.firstChild).toHaveAttribute('data-image-state', 'ready');
    expect(screen.getByRole('img', { name: 'Nature card artwork' })).toBeInTheDocument();
    expect(screen.queryByText('Loading artwork…')).toBeNull();
  });

  it('falls back after a failed image and recovers when a new release URL is supplied', () => {
    const { container, rerender } = render(<PedestalImage assetId="card-front-nature" alt="Nature card artwork" />);
    fireEvent.error(container.querySelector('img'));
    expect(container.firstChild).toHaveAttribute('data-image-state', 'error');
    expect(container.querySelector('img')).toBeNull();
    expect(screen.getByRole('img', { name: 'Nature card artwork' })).toHaveTextContent('Artwork unavailable');
    resolvePedestalImage.mockReturnValue({ ...image, url: '/private/new-release.png' });
    rerender(<PedestalImage assetId="card-front-nature" alt="Nature card artwork" />);
    expect(container.firstChild).toHaveAttribute('data-image-state', 'loading');
    fireEvent.load(container.querySelector('img'));
    expect(container.firstChild).toHaveAttribute('data-image-state', 'ready');
  });

  it('keeps decorative images and their unavailable fallback silent', () => {
    const { container, rerender } = render(<PedestalImage assetId="card-front-nature" />);
    expect(container.querySelector('img')).toHaveAttribute('alt', '');
    fireEvent.error(container.querySelector('img'));
    expect(screen.queryByRole('img')).toBeNull();
    resolvePedestalImage.mockReturnValue(null);
    rerender(<PedestalImage assetId="card-front-nature" />);
    expect(container.firstChild).toHaveAttribute('aria-hidden', 'true');
    expect(container.firstChild).toHaveAttribute('data-image-state', 'unavailable');
  });

  it('uses the actual native variant dimensions when explicitly selected', () => {
    resolvePedestalImage.mockReturnValue({ ...image, width: 1024, height: 1024, variantId: 'native' });
    const { container } = render(<PedestalImage assetId="card-front-nature" variantId="native" />);
    expect(container.querySelector('img')).toHaveAttribute('width', '1024');
    expect(container.firstChild).toHaveAttribute('data-image-variant', 'native');
  });

  it('retains frame content when private artwork is absent or fails', () => {
    resolvePedestalImage.mockReturnValue(null);
    const { container, rerender } = render(<PedestalFrame><h3>A readable application heading</h3><button>Existing action</button></PedestalFrame>);
    expect(screen.getByRole('button', { name: 'Existing action' })).toBeEnabled();
    expect(screen.getByRole('region', { name: 'Framed content' })).toHaveAttribute('tabindex', '0');
    expect(container.querySelector('[data-pedestal-frame-content="true"]')).toHaveTextContent('A readable application heading');
    resolvePedestalImage.mockReturnValue({ ...image, assetId: 'frame-gold' });
    rerender(<PedestalFrame><h3>A readable application heading</h3><button>Existing action</button></PedestalFrame>);
    fireEvent.error(container.querySelector('img'));
    expect(screen.getByRole('button', { name: 'Existing action' })).toBeEnabled();
    expect(screen.getByRole('heading', { name: 'A readable application heading' })).toBeInTheDocument();
  });
});
