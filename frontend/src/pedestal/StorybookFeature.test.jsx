import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import StorybookFeature from './StorybookFeature';
import { resolvePedestalImage } from './pedestalRelease';

vi.mock('./pedestalRelease', () => ({ resolvePedestalImage: vi.fn() }));

const image = { url: '/synthetic/card.png', width: 512, height: 512, assetId: 'card-front-light', variantId: 'web' };

beforeEach(() => resolvePedestalImage.mockReturnValue(image));

describe('Storybook feature artwork', () => {
  it('keeps the complete decorative canvas separate from readable content and actions', () => {
    const { container } = render(<StorybookFeature assetId="card-front-light"><h2>A saved challenge</h2><button>View challenge</button></StorybookFeature>);
    const artwork = container.querySelector('img');
    expect(artwork).toHaveAttribute('width', '512');
    expect(artwork).toHaveAttribute('height', '512');
    expect(artwork).toHaveAttribute('alt', '');
    expect(artwork.closest('[aria-hidden="true"]')).not.toContainElement(screen.getByRole('button', { name: 'View challenge' }));
    expect(screen.queryByRole('img')).not.toBeInTheDocument();
  });

  it('preserves the action when artwork fails and recovers with a new release URL', () => {
    const onView = vi.fn();
    const content = <StorybookFeature assetId="card-front-light"><button onClick={onView}>View challenge</button></StorybookFeature>;
    const { container, rerender } = render(content);
    fireEvent.error(container.querySelector('img'));
    expect(container.querySelector('img')).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: 'View challenge' }));
    expect(onView).toHaveBeenCalledOnce();
    resolvePedestalImage.mockReturnValue({ ...image, url: '/synthetic/new-card.png' });
    rerender(<StorybookFeature assetId="card-front-light"><button onClick={onView}>View challenge</button></StorybookFeature>);
    expect(container.querySelector('img')).toHaveAttribute('src', '/synthetic/new-card.png');
  });

  it.each([undefined, 'card-front-light'])('keeps normal content available when private artwork is absent (%s)', (assetId) => {
    resolvePedestalImage.mockReturnValue(null);
    const { container } = render(<StorybookFeature assetId={assetId}><h2>Run 2 miles this week</h2><button>Log a run</button></StorybookFeature>);
    expect(container.querySelector('img')).toBeNull();
    expect(screen.getByRole('heading', { name: 'Run 2 miles this week' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Log a run' })).toBeEnabled();
    expect(screen.queryByText('Artwork unavailable')).not.toBeInTheDocument();
  });
});
