import { beforeEach, describe, it, expect, vi } from 'vitest';
import { renderWithProviders, screen, userEvent } from '../../test/render';
import { resolvePedestalImage } from '../../pedestal/pedestalRelease';
import TrophySlot from './TrophySlot';

vi.mock('../../pedestal/pedestalRelease', () => ({ resolvePedestalImage: vi.fn() }));

beforeEach(() => { resolvePedestalImage.mockReturnValue(null); });

describe('TrophySlot', () => {
  it('renders the empty-state with an accessible prompt', () => {
    renderWithProviders(<TrophySlot badge={null} onOpen={() => {}} />);
    const btn = screen.getByRole('button');
    expect(btn.getAttribute('aria-label')).toMatch(/no trophy badge/i);
    expect(screen.getByText('Choose an earned badge')).toBeInTheDocument();
  });

  it('renders the occupied-state with badge name + rarity chip', () => {
    const badge = { id: 1, name: 'Centennial', rarity: 'legendary', icon: '\ud83d\udc8e' };
    renderWithProviders(<TrophySlot badge={badge} onOpen={() => {}} />);
    expect(screen.getByText('Centennial')).toBeInTheDocument();
    expect(screen.getByText('legendary')).toBeInTheDocument();
    expect(screen.getByText('Your trophy badge')).toBeInTheDocument();
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

  it('keeps earned trophy identity and the picker action in its compact layout', async () => {
    const user = userEvent.setup();
    const onOpen = vi.fn();
    renderWithProviders(<TrophySlot compact badge={{ id: 1, name: 'First Project', icon: '⭐', rarity: 'common' }} onOpen={onOpen} />);
    expect(screen.getByText('First Project')).toBeInTheDocument();
    expect(screen.getByText('Your trophy badge')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: /Trophy badge: First Project/i }));
    expect(onOpen).toHaveBeenCalledTimes(1);
  });

  it('keeps the actual earned icon and one keyboard picker action inside the wide canvas', async () => {
    const user = userEvent.setup();
    const onOpen = vi.fn();
    const { container } = renderWithProviders(
      <TrophySlot compact badge={{ id: 7, name: 'Night Owl', icon: '🦉', rarity: 'rare' }} onOpen={onOpen} />,
    );
    expect(container.querySelector('[data-achievement-card="wide"]')).toBe(screen.getByRole('button'));
    expect(container.querySelector('[data-badge-artwork="tile"]')).toBeInTheDocument();
    expect(container.querySelector('[data-pedestal-image="frame-gold"]')).toBeNull();
    expect(screen.getByText('🦉')).toBeInTheDocument();
    expect(screen.getByText('rare')).toBeInTheDocument();
    expect(screen.getAllByRole('button')).toHaveLength(1);
    expect(screen.queryByRole('region')).toBeNull();
    await user.tab();
    expect(screen.getByRole('button', { name: /Trophy badge: Night Owl/ })).toHaveFocus();
    await user.keyboard('{Enter}');
    expect(onOpen).toHaveBeenCalledTimes(1);
    expect(resolvePedestalImage).not.toHaveBeenCalled();
  });

  it('keeps a long earned identity and change action available', async () => {
    const user = userEvent.setup();
    const onOpen = vi.fn();
    const name = 'A very long earned badge name that stays beside its artwork';
    const { container } = renderWithProviders(
      <TrophySlot compact badge={{ id: 7, name, icon: '🦉', rarity: 'rare' }} onOpen={onOpen} />,
    );
    expect(container.querySelector('[data-achievement-card="wide"]')).toBeInTheDocument();
    expect(screen.getByText(name)).toBeInTheDocument();
    expect(screen.getByText('🦉')).toBeInTheDocument();
    expect(screen.getByText('rare')).toBeInTheDocument();
    expect(screen.getByText('Change')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: `Trophy badge: ${name}. Click to change or clear.` }));
    expect(onOpen).toHaveBeenCalledTimes(1);
  });

  it('keeps the empty wide canvas with its choose action available', async () => {
    const user = userEvent.setup();
    const onOpen = vi.fn();
    const { container } = renderWithProviders(<TrophySlot compact badge={null} onOpen={onOpen} />);
    expect(container.querySelector('[data-pedestal-image="frame-gold"]')).toBeNull();
    expect(screen.getByText('Choose an earned badge')).toBeInTheDocument();
    expect(screen.getByText('Choose')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: /No trophy badge chosen/ }));
    expect(onOpen).toHaveBeenCalledTimes(1);
  });

  it('preserves the complete long badge identity and keyboard picker action in the full layout', async () => {
    const name = 'AnExtraordinarilyLongUnbrokenAchievementNameThatMustRemainReadable';
    const user = userEvent.setup();
    const onOpen = vi.fn();
    renderWithProviders(<TrophySlot badge={{ id: 12, name, icon: '🦉', rarity: 'epic' }} onOpen={onOpen} />);
    expect(screen.getByText(name)).toBeInTheDocument();
    expect(screen.getByText('epic')).toBeInTheDocument();
    const button = screen.getByRole('button', { name: `Trophy badge: ${name}. Click to change or clear.` });
    await user.tab();
    expect(button).toHaveFocus();
    await user.keyboard(' ');
    expect(onOpen).toHaveBeenCalledTimes(1);
  });
});
