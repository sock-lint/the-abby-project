import { describe, it, expect, vi } from 'vitest';
import { renderWithProviders, screen, userEvent } from '../../test/render';
import TrophySlot from './TrophySlot';

describe('TrophySlot', () => {
  it('renders the empty-state with an accessible prompt', () => {
    renderWithProviders(<TrophySlot badge={null} onOpen={() => {}} />);
    const btn = screen.getByRole('button');
    expect(btn.getAttribute('aria-label')).toMatch(/no hero seal/i);
    expect(screen.getByText(/choose from your reliquary/i)).toBeInTheDocument();
  });

  it('renders the occupied-state with badge name + rarity chip', () => {
    const badge = { id: 1, name: 'Centennial', rarity: 'legendary', icon: '\ud83d\udc8e' };
    renderWithProviders(<TrophySlot badge={badge} onOpen={() => {}} />);
    expect(screen.getByText('Centennial')).toBeInTheDocument();
    expect(screen.getByText('legendary')).toBeInTheDocument();
    expect(screen.getByText(/your hero seal/i)).toBeInTheDocument();
  });

  it('fires onOpen when clicked', async () => {
    const user = userEvent.setup();
    const spy = vi.fn();
    renderWithProviders(<TrophySlot badge={null} onOpen={spy} />);
    await user.click(screen.getByRole('button'));
    expect(spy).toHaveBeenCalledTimes(1);
  });

  it('tags the filled state via data attribute', () => {
    const { container } = renderWithProviders(
      <TrophySlot
        badge={{ id: 1, name: 'Foo', rarity: 'rare', icon: '\ud83c\udfc6' }}
        onOpen={() => {}}
      />,
    );
    const slot = container.querySelector('[data-trophy-slot="true"]');
    expect(slot?.getAttribute('data-filled')).toBe('true');
  });
});
