import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import CatalogCard from './CatalogCard.jsx';

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
});
