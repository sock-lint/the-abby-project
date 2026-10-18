import { describe, it, expect, vi } from 'vitest';
import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { renderWithProviders } from '../test/render';
import RareDropReveal from './RareDropReveal';

const legendaryDrop = {
  id: 7,
  item_name: 'Cosmic Phoenix Egg',
  item_rarity: 'legendary',
  item_icon: '🥚',
  was_salvaged: false,
};

describe('RareDropReveal', () => {
  it('renders legendary tier label and item name', () => {
    renderWithProviders(
      <RareDropReveal drop={legendaryDrop} onDismiss={() => {}} />,
    );
    expect(screen.getByRole('alertdialog')).toBeInTheDocument();
    expect(screen.getByText(/legendary drop/i)).toBeInTheDocument();
    expect(screen.getByText(/cosmic phoenix egg/i)).toBeInTheDocument();
    expect(screen.getByText(/added to your inventory/i)).toBeInTheDocument();
  });

  it('shows salvage copy when drop is a duplicate cosmetic', () => {
    renderWithProviders(
      <RareDropReveal
        drop={{ ...legendaryDrop, was_salvaged: true }}
        onDismiss={() => {}}
      />,
    );
    expect(screen.getByText(/salvaged for coins/i)).toBeInTheDocument();
  });

  it('calls onDismiss with the drop id when Continue clicked', async () => {
    const onDismiss = vi.fn();
    const user = userEvent.setup();
    renderWithProviders(
      <RareDropReveal drop={legendaryDrop} onDismiss={onDismiss} />,
    );
    await user.click(screen.getByRole('button', { name: /continue/i }));
    expect(onDismiss).toHaveBeenCalledWith(7);
  });

  it('renders nothing for non-rare drop', () => {
    const { container } = renderWithProviders(
      <RareDropReveal
        drop={{ ...legendaryDrop, item_rarity: 'common' }}
        onDismiss={() => {}}
      />,
    );
    expect(container.querySelector('[role="alertdialog"]')).toBeNull();
  });

  it.each([
    ['cosmetic_frame', {}, 'Choose profile frame', '/sigil'],
    ['cosmetic_theme', {}, 'Change color theme', '/settings#appearance'],
    ['egg', {}, 'Go to hatching', '/bestiary?tab=hatchery'],
    ['food', {}, 'Feed a pet', '/bestiary?tab=companions'],
    ['coin_pouch', { coins: 75 }, 'Open in inventory', '/treasury?tab=satchel'],
    ['consumable', { effect: 'drop_boost' }, 'Use in inventory', '/treasury?tab=satchel'],
  ])('explains a %s and links to its next action without consuming it', async (item_type, item_metadata, label, path) => {
    const onDismiss = vi.fn();
    const { user } = renderWithProviders(<RareDropReveal drop={{
      ...legendaryDrop, item_type, item_metadata,
      item_description: 'A useful reward from your progress.', item_catalog_available: true,
      item_effect_summary: 'Server-confirmed reward effect.',
    }} onDismiss={onDismiss} />);
    expect(screen.getByText('A useful reward from your progress.')).toBeInTheDocument();
    expect(screen.getByText('Server-confirmed reward effect.')).toBeInTheDocument();
    const action = screen.getByRole('link', { name: label });
    expect(action).toHaveAttribute('href', path);
    await user.click(action);
    expect(onDismiss).toHaveBeenCalledWith(legendaryDrop.id);
  });

  it.each([0, 25])('shows the exact confirmed salvage amount (%s) without an equip action', (salvage_coins) => {
    renderWithProviders(<RareDropReveal drop={{ ...legendaryDrop, item_type: 'cosmetic_frame', was_salvaged: true, salvage_coins }} />);
    expect(screen.getByText(`Already in your collection · exchanged for ${salvage_coins} coins.`)).toBeInTheDocument();
    expect(screen.queryByRole('link', { name: 'Choose profile frame' })).toBeNull();
  });

  it('keeps historical unknown salvage amounts unknown and unavailable items view-only', () => {
    renderWithProviders(<RareDropReveal drop={{ ...legendaryDrop, item_type: 'cosmetic_frame', item_catalog_available: false, salvage_coins: null }} />);
    expect(screen.queryByRole('link', { name: 'Choose profile frame' })).toBeNull();
    expect(screen.getByRole('link', { name: 'View inventory' })).toHaveAttribute('href', '/treasury?tab=satchel');
  });

  it('does not invent an amount for a historical salvage receipt', () => {
    renderWithProviders(<RareDropReveal drop={{ ...legendaryDrop, was_salvaged: true, salvage_coins: null }} />);
    expect(screen.getByText('Already in your collection — salvaged for coins.')).toBeInTheDocument();
    expect(screen.queryByText(/exchanged for \d+ coins/)).toBeNull();
  });
});
