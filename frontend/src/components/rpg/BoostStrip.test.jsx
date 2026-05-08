import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import BoostStrip from './BoostStrip';

describe('BoostStrip', () => {
  it('renders nothing when no boosts are active', () => {
    const { container } = render(
      <BoostStrip
        profile={{
          xp_boost_seconds_remaining: null,
          coin_boost_seconds_remaining: null,
          drop_boost_seconds_remaining: null,
          pet_growth_boost_remaining: 0,
        }}
      />,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it('renders a chip for each active boost', () => {
    render(
      <BoostStrip
        profile={{
          xp_boost_seconds_remaining: 7200,
          coin_boost_seconds_remaining: null,
          drop_boost_seconds_remaining: 90,
          pet_growth_boost_remaining: 3,
        }}
      />,
    );
    expect(screen.getByText('XP boost')).toBeInTheDocument();
    expect(screen.getByText('2h')).toBeInTheDocument();
    expect(screen.getByText('Drop boost')).toBeInTheDocument();
    expect(screen.getByText('1m30s')).toBeInTheDocument();
    expect(screen.getByText('Pet growth')).toBeInTheDocument();
    expect(screen.getByText('× 3')).toBeInTheDocument();
    expect(screen.queryByText('Coin boost')).not.toBeInTheDocument();
  });

  it('uses status role with a count-aware aria-label', () => {
    render(
      <BoostStrip
        profile={{ xp_boost_seconds_remaining: 60, pet_growth_boost_remaining: 2 }}
      />,
    );
    const strip = screen.getByRole('status');
    expect(strip).toHaveAttribute('aria-label', '2 active boons');
  });

  it('null/undefined profile collapses to nothing', () => {
    const { container: a } = render(<BoostStrip profile={null} />);
    expect(a).toBeEmptyDOMElement();
    const { container: b } = render(<BoostStrip profile={undefined} />);
    expect(b).toBeEmptyDOMElement();
  });
});
