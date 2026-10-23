import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render } from '@testing-library/react';
import HeaderStreakFlame from './HeaderStreakFlame';
import { resolveStreakFlame } from '../../streak/streakFlameRelease';

vi.mock('../../streak/streakFlameRelease', () => ({ resolveStreakFlame: vi.fn() }));
const syntheticUrl = (stage) => `data:image/svg+xml,${encodeURIComponent(`<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24"><title>Synthetic ${stage}</title><circle cx="12" cy="12" r="1"/></svg>`)}`;

beforeEach(() => resolveStreakFlame.mockImplementation((stage) => stage === 'unknown' ? null : { url: syntheticUrl(stage) }));

describe('HeaderStreakFlame', () => {
  it.each([20, 24])('renders the complete authored image document at %ipx without a numeric overlay', (size) => {
    const { container } = render(<HeaderStreakFlame stage="maximum-blaze" size={size} />);
    const image = container.querySelector('img');
    expect(image).toHaveAttribute('width', String(size));
    expect(image).toHaveAttribute('height', String(size));
    expect(image).toHaveAttribute('alt', '');
    expect(image).toHaveAttribute('src', syntheticUrl('maximum-blaze'));
    expect(image.parentElement).toHaveAttribute('aria-hidden', 'true');
    expect(image.parentElement).toHaveAttribute('data-artwork-status', 'ready');
    expect(image.parentElement.textContent).toBe('');
    expect(container.querySelector('[id]')).toBeNull();
  });

  it('keeps unknown data distinct from the known dormant artwork', () => {
    const { container, rerender } = render(<HeaderStreakFlame />);
    expect(container.querySelector('[data-header-streak-flame]')).toHaveAttribute('data-state', 'unknown');
    expect(container.querySelector('img')).toBeNull();
    rerender(<HeaderStreakFlame stage="dormant-ember" />);
    expect(container.querySelector('img')).toHaveAttribute('src', syntheticUrl('dormant-ember'));
  });

  it('keeps the text-independent canvas usable when private artwork is absent or fails to decode', () => {
    resolveStreakFlame.mockReturnValueOnce(null);
    const { container, rerender } = render(<HeaderStreakFlame stage="small-flame" />);
    expect(container.querySelector('[data-artwork-status]')).toHaveAttribute('data-artwork-status', 'unavailable');
    expect(container.querySelector('img')).toBeNull();
    rerender(<HeaderStreakFlame stage="small-flame" />);
    fireEvent.error(container.querySelector('img'));
    expect(container.querySelector('img')).toBeNull();
    expect(container.querySelector('[data-artwork-status]')).toHaveAttribute('data-artwork-status', 'unavailable');
    rerender(<HeaderStreakFlame stage="strong-flame" />);
    expect(container.querySelector('img')).toHaveAttribute('src', syntheticUrl('strong-flame'));
  });
});
