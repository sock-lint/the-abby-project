import { beforeEach, describe, it, expect, vi } from 'vitest';
import { fireEvent, renderWithProviders, screen, userEvent } from '../../test/render';
import { resolvePedestalImage } from '../../pedestal/pedestalRelease';
import TrophySlot from './TrophySlot';

vi.mock('../../pedestal/pedestalRelease', () => ({ resolvePedestalImage: vi.fn() }));

beforeEach(() => resolvePedestalImage.mockReturnValue(null));

describe('TrophySlot', () => {
  it('uses the equipped frame’s whole Nature card beside the real earned badge', () => {
    const frame = { id: 14, name: "Ranger's Cap Frame", metadata: { card_asset_id: 'card-front-nature' } };
    const { container } = renderWithProviders(<TrophySlot compact frame={frame}
      badge={{ id: 7, name: 'Night Owl', rarity: 'rare', icon: '🦉' }} onOpen={() => {}} />);
    expect(container.querySelector('[data-pedestal-image="card-front-nature"]')).not.toBeNull();
    expect(screen.getByText('Night Owl')).toBeInTheDocument();
    expect(screen.getByText('🦉')).toBeInTheDocument();
    expect(screen.getByText('Nature card style')).toBeInTheDocument();
  });
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

  it('shows the equipped whole Light card without adding a focus target or replacing badge identity', async () => {
    resolvePedestalImage.mockReturnValue({
      assetId: 'card-front-light', variantId: 'web', url: '/private/synthetic-card.png', width: 512, height: 512,
    });
    const user = userEvent.setup();
    const onOpen = vi.fn();
    const { container } = renderWithProviders(
      <TrophySlot compact frame={{ metadata: { card_asset_id: 'card-front-light' } }} badge={{ id: 7, name: 'Night Owl', icon: '🦉', rarity: 'rare' }} onOpen={onOpen} />,
    );
    const frame = container.querySelector('[data-pedestal-image="card-front-light"]');
    expect(frame.querySelector('img')).toHaveAttribute('alt', '');
    expect(frame.querySelector('img')).toHaveAttribute('width', '512');
    expect(frame.querySelector('img')).toHaveAttribute('height', '512');
    expect(screen.getByText('🦉')).toBeInTheDocument();
    expect(screen.getByText('rare')).toBeInTheDocument();
    expect(screen.getAllByRole('button')).toHaveLength(1);
    expect(screen.queryByRole('region')).toBeNull();
    await user.tab();
    expect(screen.getByRole('button', { name: /Trophy badge: Night Owl/ })).toHaveFocus();
    await user.keyboard('{Enter}');
    expect(onOpen).toHaveBeenCalledTimes(1);
  });

  it('keeps the earned name, icon, rarity and change action readable when card artwork fails', async () => {
    resolvePedestalImage.mockReturnValue({
      assetId: 'card-front-nature', variantId: 'web', url: '/private/synthetic-card.png', width: 512, height: 512,
    });
    const user = userEvent.setup();
    const onOpen = vi.fn();
    const name = 'A very long earned badge name that stays beside its artwork';
    const { container } = renderWithProviders(
      <TrophySlot compact frame={{ metadata: { card_asset_id: 'card-front-nature' } }} badge={{ id: 7, name, icon: '🦉', rarity: 'rare' }} onOpen={onOpen} />,
    );
    fireEvent.error(container.querySelector('img'));
    expect(container.querySelector('[data-pedestal-image="card-front-nature"]')).toHaveAttribute('data-image-state', 'error');
    expect(screen.getByText(name)).toBeInTheDocument();
    expect(screen.getByText('🦉')).toBeInTheDocument();
    expect(screen.getByText('rare')).toBeInTheDocument();
    expect(screen.getByText('Change')).toBeInTheDocument();
    expect(screen.getByText('Nature card style')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: `Trophy badge: ${name}. Click to change or clear.` }));
    expect(onOpen).toHaveBeenCalledTimes(1);
  });

  it('leaves the compact empty slot unframed with its choose action available', async () => {
    const user = userEvent.setup();
    const onOpen = vi.fn();
    const { container } = renderWithProviders(<TrophySlot compact badge={null} onOpen={onOpen} />);
    expect(container.querySelector('[data-pedestal-image="frame-gold"]')).toBeNull();
    expect(screen.getByText('Choose an earned badge')).toBeInTheDocument();
    expect(screen.getByText('Choose')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: /No trophy badge chosen/ }));
    expect(onOpen).toHaveBeenCalledTimes(1);
  });

  it('keeps an unbound equipped frame quiet without inventing a gold surround', () => {
    const { container } = renderWithProviders(<TrophySlot compact
      frame={{ name: 'Gold Frame', metadata: { border_color: '#866329' } }}
      badge={{ id: 1, name: 'First Project', icon: '⭐', rarity: 'common' }} onOpen={() => {}} />);
    expect(container.querySelector('[data-pedestal-image]')).toBeNull();
    expect(screen.getByText('First Project')).toBeInTheDocument();
    expect(screen.getByText('⭐')).toBeInTheDocument();
  });

  it('keeps choosing an earned badge available even with a card style and no trophy', async () => {
    const user = userEvent.setup();
    const onOpen = vi.fn();
    renderWithProviders(<TrophySlot compact frame={{ metadata: { card_asset_id: 'card-front-light' } }} badge={null} onOpen={onOpen} />);
    expect(screen.getByText('Light card style')).toBeInTheDocument();
    expect(screen.queryByText('rare')).toBeNull();
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
