import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import { CoinIcon, TreasuryIcon, TodayIcon, QuestsIcon, BestiaryIcon, AtlasIcon, ChronicleIcon } from './JournalIcons';

describe('Meadow icons', () => {
  it('preserves caller sizes and classes while keeping labelled controls accessible', () => {
    const { container } = render(<button><CoinIcon size={14} className="text-gold-leaf" />Adjust coins</button>);
    expect(screen.getByRole('button', { name: 'Adjust coins' })).toBeInTheDocument();
    const icon = container.querySelector('svg');
    expect(icon).toHaveAttribute('width', '14');
    expect(icon).toHaveAttribute('height', '14');
    expect(icon).toHaveClass('text-gold-leaf');
    expect(icon).toHaveAttribute('aria-hidden', 'true');
    expect(icon).toHaveAttribute('focusable', 'false');
  });

  it('gives each chapter its own drawing and keeps treasury distinct from coins', () => {
    const { container } = render(<><TodayIcon /><QuestsIcon /><BestiaryIcon /><TreasuryIcon /><AtlasIcon /><ChronicleIcon /><CoinIcon /></>);
    expect([...container.querySelectorAll('svg')].map((icon) => icon.dataset.meadowIcon)).toEqual([
      'home', 'adventure', 'companions', 'treasure', 'atlas', 'memories', 'coin',
    ]);
  });
});
