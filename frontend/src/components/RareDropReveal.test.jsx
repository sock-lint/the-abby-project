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
    expect(screen.getByText(/added to your satchel/i)).toBeInTheDocument();
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
});
