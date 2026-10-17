import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import StarRating from './StarRating.jsx';
import { resolvePedestalImage } from '../pedestal/pedestalRelease';

vi.mock('../pedestal/pedestalRelease', () => ({ resolvePedestalImage: vi.fn() }));
beforeEach(() => resolvePedestalImage.mockReturnValue(null));

describe('StarRating', () => {
  it('uses a supplied effort label once without repeating its numeric value', () => {
    render(<StarRating value={3} title="Effort: 3/5" />);
    expect(screen.getByRole('img', { name: 'Effort: 3/5' })).toBeInTheDocument();
  });

  it('keeps the numeric difficulty accessible when its art loads or fails', () => {
    resolvePedestalImage.mockImplementation((assetId) => ({
      assetId, url: `/synthetic/${assetId}.png`, variantId: 'web', width: 512, height: 512,
    }));
    const { container } = render(<StarRating value={3} />);
    expect(screen.getByRole('img', { name: 'Difficulty: 3 out of 5' })).toBeInTheDocument();
    expect(container.querySelectorAll('[data-pedestal-image="star-lit"]')).toHaveLength(3);
    expect(container.querySelectorAll('[data-pedestal-image="star-unlit"]')).toHaveLength(2);
    const art = container.querySelector('img');
    expect(art).toHaveAttribute('alt', '');
    fireEvent.load(art);
    expect(screen.getByRole('img', { name: 'Difficulty: 3 out of 5' })).toBeInTheDocument();
    fireEvent.error(art);
    expect(container).toHaveTextContent('★');
    expect(screen.getByRole('img', { name: 'Difficulty: 3 out of 5' })).toBeInTheDocument();
  });

  it('renders filled plus empty stars to the configured max', () => {
    const { container } = render(<StarRating value={3} max={5} />);
    expect(container.textContent).toBe('★★★☆☆');
  });

  it('clamps value above max', () => {
    const { container } = render(<StarRating value={7} max={5} />);
    expect(container.textContent).toBe('★★★★★');
  });

  it('clamps negative values to zero', () => {
    const { container } = render(<StarRating value={-2} max={3} />);
    expect(container.textContent).toBe('☆☆☆');
  });

  it('uses default max when omitted', () => {
    const { container } = render(<StarRating value={0} />);
    expect(container.textContent.length).toBe(5);
  });

  it('applies title attribute when provided', () => {
    render(<StarRating value={1} title="Difficulty" />);
    expect(screen.getByTitle('Difficulty')).toBeInTheDocument();
  });

  it('accepts a custom className', () => {
    const { container } = render(<StarRating value={1} className="extra" />);
    expect(container.firstChild.className).toContain('extra');
  });
});
