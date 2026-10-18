import { fireEvent, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import AchievementCard from './AchievementCard';
import AchievementCardIcon from './AchievementCardIcon';
import { resolveAchievementCardImage } from '../../avatar/achievementCardKit';

vi.mock('../../avatar/achievementCardKit', () => ({ resolveAchievementCardImage: vi.fn() }));
const image = (id, variant, suffix = '') => ({ assetId: id, variantId: variant,
  url: `/synthetic/${id}${suffix}.png`, width: variant === 'icon-512' ? 512 : 1024,
  height: variant === 'tall' ? 1280 : 512 });

beforeEach(() => {
  resolveAchievementCardImage.mockImplementation((id, variant) => image(id, variant));
});

describe('AchievementCard', () => {
  it('preserves live text and actions before artwork loads, then displays a matching pair', async () => {
    const onChoose = vi.fn();
    const { container } = render(<AchievementCard variant="wide"><h2>Thoughtful creator</h2>
      <button onClick={onChoose}>Choose badge</button></AchievementCard>);
    const card = container.querySelector('[data-achievement-card]');
    expect(card).toHaveAttribute('data-achievement-card-art', 'pending');
    await userEvent.click(screen.getByRole('button', { name: 'Choose badge' }));
    expect(onChoose).toHaveBeenCalledOnce();
    const images = container.querySelectorAll('img');
    expect(images[0]).toHaveAttribute('src', '/synthetic/abby-card-base-wide.png');
    expect(images[1]).toHaveAttribute('src', '/synthetic/abby-card-border-gold-wide.png');
    fireEvent.load(images[0]);
    expect(card).toHaveAttribute('data-achievement-card-art', 'pending');
    fireEvent.load(images[1]);
    expect(card).toHaveAttribute('data-achievement-card-art', 'ready');
    expect(screen.getByRole('heading', { name: 'Thoughtful creator' })).toBeVisible();
  });

  it('keeps a usable fallback when either half of a tall pair fails', async () => {
    const onCollect = vi.fn();
    const { container } = render(<AchievementCard variant="tall"><p>A saved reward</p>
      <button onClick={onCollect}>Collect reward</button></AchievementCard>);
    const images = container.querySelectorAll('img');
    expect(images[0]).toHaveAttribute('height', '1280');
    expect(images[1]).toHaveAttribute('src', '/synthetic/abby-card-border-gold-tall.png');
    fireEvent.load(images[0]);
    fireEvent.error(images[1]);
    expect(container.querySelector('[data-achievement-card]')).toHaveAttribute('data-achievement-card-art', 'unavailable');
    expect(container.querySelector('[data-achievement-card-layer]')).toBeNull();
    await userEvent.click(screen.getByRole('button', { name: 'Collect reward' }));
    expect(onCollect).toHaveBeenCalledOnce();
  });

  it('retains button semantics and live badge identity without private assets', async () => {
    resolveAchievementCardImage.mockReturnValue(null);
    const onChoose = vi.fn();
    render(<AchievementCard as="button" type="button" aria-label="Night Owl · rare" onClick={onChoose}>
      <span>Night Owl</span><span>rare</span></AchievementCard>);
    const button = screen.getByRole('button', { name: 'Night Owl · rare' });
    expect(button).toHaveAttribute('data-achievement-card-art', 'unavailable');
    await userEvent.click(button);
    expect(onChoose).toHaveBeenCalledOnce();
  });

  it('recovers a failed pair when a new release supplies fresh image URLs', () => {
    const { container, rerender } = render(<AchievementCard>Achievement</AchievementCard>);
    fireEvent.error(container.querySelector('img'));
    expect(container.querySelector('[data-achievement-card]')).toHaveAttribute('data-achievement-card-art', 'unavailable');
    resolveAchievementCardImage.mockImplementation((id, variant) => image(id, variant, '-new'));
    rerender(<AchievementCard>Achievement</AchievementCard>);
    container.querySelectorAll('img').forEach((img) => fireEvent.load(img));
    expect(container.querySelector('[data-achievement-card]')).toHaveAttribute('data-achievement-card-art', 'ready');
  });
});

describe('AchievementCardIcon', () => {
  it('keeps the complete icon canvas and an explicit contextual label', () => {
    const { container } = render(<AchievementCardIcon icon="book" size={24} label="Reading" />);
    expect(screen.getByRole('img', { name: 'Reading' })).toHaveStyle({ width: '24px', height: '24px' });
    expect(container.querySelector('img')).toHaveAttribute('src', '/synthetic/abby-icon-book.png');
    expect(container.querySelector('img')).toHaveAttribute('width', '512');
  });

  it('retains its accessible label and fallback when a contextual icon fails', () => {
    const { container } = render(<AchievementCardIcon icon="heart" label="Kindness" fallback={<span>Heart</span>} />);
    fireEvent.error(container.querySelector('img'));
    expect(screen.getByRole('img', { name: 'Kindness' })).toHaveTextContent('Heart');
    expect(container.querySelector('img')).toBeNull();
  });

  it('does not resolve unregistered icons into badge assignments', () => {
    render(<AchievementCardIcon icon="badge-night-owl" fallback={<span>Original badge icon</span>} />);
    expect(screen.getByText('Original badge icon')).toBeVisible();
    expect(resolveAchievementCardImage).not.toHaveBeenCalled();
  });
});
