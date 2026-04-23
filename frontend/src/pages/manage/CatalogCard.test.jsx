import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import CatalogCard from './CatalogCard.jsx';

// Mock RpgSprite so we can assert what props CatalogCard forwards without
// standing up the SpriteCatalogProvider. The real component is exercised
// elsewhere; here we only care about the prop pipeline.
vi.mock('../../components/rpg/RpgSprite', () => ({
  default: ({ spriteKey, fallbackSpriteKey, alt }) => (
    <span
      data-testid="rpg-sprite"
      data-spritekey={spriteKey || ''}
      data-fallback={fallbackSpriteKey || ''}
      aria-label={alt}
    />
  ),
}));

describe('CatalogCard', () => {
  it('renders name + subtitle and fires onClick when tapped', async () => {
    const onClick = vi.fn();
    const user = userEvent.setup();
    render(
      <CatalogCard
        rarity="rare"
        icon="🥚"
        spriteKey={null}
        name="Dragon Egg"
        subtitle="rare"
        onClick={onClick}
      />,
    );
    expect(screen.getByText('Dragon Egg')).toBeInTheDocument();
    expect(screen.getByText('rare')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: /dragon egg/i }));
    expect(onClick).toHaveBeenCalledTimes(1);
  });

  it('omits the subtitle line when no subtitle is provided', () => {
    render(
      <CatalogCard
        rarity="common"
        icon="🥚"
        spriteKey={null}
        name="Plain Egg"
        onClick={vi.fn()}
      />,
    );
    expect(screen.getByText('Plain Egg')).toBeInTheDocument();
    // Only one text node (the name); no subtitle line rendered.
    expect(screen.queryByText(/^common$/)).toBeNull();
  });

  it('forwards fallbackSpriteKey to RpgSprite', () => {
    render(
      <CatalogCard
        rarity="rare"
        icon="🐉"
        spriteKey="dragon-mount"
        fallbackSpriteKey="dragon"
        name="Dragon mount"
        onClick={vi.fn()}
      />,
    );
    const sprite = screen.getByTestId('rpg-sprite');
    expect(sprite.dataset.spritekey).toBe('dragon-mount');
    expect(sprite.dataset.fallback).toBe('dragon');
  });
});
