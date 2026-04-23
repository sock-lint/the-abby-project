import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import MountsBlock from './MountsBlock.jsx';

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

describe('MountsBlock', () => {
  it('renders empty state with no species', () => {
    render(<MountsBlock species={[]} onSelect={vi.fn()} />);
    expect(screen.getByRole('status')).toBeInTheDocument();
    expect(screen.getByText(/no pet species/i)).toBeInTheDocument();
  });

  it('renders one card per species using the -mount slug with fallback', () => {
    render(
      <MountsBlock
        species={[
          { id: 1, name: 'Fox', sprite_key: 'fox', icon: '🦊' },
          { id: 2, name: 'Wolf', sprite_key: 'wolf', icon: '🐺' },
        ]}
        onSelect={vi.fn()}
      />,
    );
    const sprites = screen.getAllByTestId('rpg-sprite');
    expect(sprites).toHaveLength(2);
    // Mount sprite uses the -mount convention; fallback is the base species key.
    expect(sprites[0].dataset.spritekey).toBe('fox-mount');
    expect(sprites[0].dataset.fallback).toBe('fox');
    expect(sprites[1].dataset.spritekey).toBe('wolf-mount');
    expect(sprites[1].dataset.fallback).toBe('wolf');
    // Every tile shows the "mount" subtitle
    expect(screen.getAllByText('mount')).toHaveLength(2);
  });

  it('fires onSelect with the species when a tile is clicked', async () => {
    const onSelect = vi.fn();
    const user = userEvent.setup();
    const fox = { id: 1, name: 'Fox', sprite_key: 'fox', icon: '🦊' };
    render(<MountsBlock species={[fox]} onSelect={onSelect} />);

    await user.click(screen.getByRole('button', { name: /fox/i }));
    expect(onSelect).toHaveBeenCalledWith(fox);
  });
});
