import { afterEach, beforeEach, describe, it, expect, vi } from 'vitest';
import { act, cleanup, render, screen } from '@testing-library/react';
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

describe('BoostStrip countdown receipts', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date('2026-10-16T12:00:00Z'));
  });

  afterEach(() => {
    cleanup();
    vi.useRealTimers();
  });

  it('keeps a fresh server duration after elapsed time and a profile refetch', () => {
    const { rerender } = render(<BoostStrip profile={{ xp_boost_seconds_remaining: 600 }} />);
    expect(screen.getByText('10m')).toBeInTheDocument();
    act(() => vi.advanceTimersByTime(120000));
    expect(screen.getByText('8m')).toBeInTheDocument();
    rerender(<BoostStrip profile={{ xp_boost_seconds_remaining: 480 }} />);
    expect(screen.getByText('8m')).toBeInTheDocument();
    act(() => vi.advanceTimersByTime(1000));
    expect(screen.getByText('7m59s')).toBeInTheDocument();
  });

  it('starts an extended boost from its newly confirmed duration', () => {
    const { rerender } = render(<BoostStrip profile={{ coin_boost_seconds_remaining: 600 }} />);
    act(() => vi.advanceTimersByTime(120000));
    rerender(<BoostStrip profile={{ coin_boost_seconds_remaining: 1200 }} />);
    expect(screen.getByText('20m')).toBeInTheDocument();
    act(() => vi.advanceTimersByTime(1000));
    expect(screen.getByText('19m59s')).toBeInTheDocument();
  });

  it('anchors a new boost even when the component previously had no timer', () => {
    const { rerender } = render(<BoostStrip profile={{}} />);
    act(() => vi.advanceTimersByTime(120000));
    rerender(<BoostStrip profile={{ drop_boost_seconds_remaining: 600 }} />);
    expect(screen.getByText('10m')).toBeInTheDocument();
    act(() => vi.advanceTimersByTime(1000));
    expect(screen.getByText('9m59s')).toBeInTheDocument();
  });

  it('does not reset elapsed time on an unrelated render of the same receipt', () => {
    const profile = { xp_boost_seconds_remaining: 600 };
    const { rerender } = render(<BoostStrip profile={profile} />);
    act(() => vi.advanceTimersByTime(120000));
    rerender(<BoostStrip profile={profile} className="extra-class" />);
    expect(screen.getByText('8m')).toBeInTheDocument();
    act(() => vi.advanceTimersByTime(1000));
    expect(screen.getByText('7m59s')).toBeInTheDocument();
  });

  it('uses the absolute expiry when a receipt also supplies relative seconds', () => {
    const { rerender } = render(<BoostStrip profile={{
      xp_boost_expires_at: '2026-10-16T12:10:00Z', xp_boost_seconds_remaining: 60,
    }} />);
    expect(screen.getByText('10m')).toBeInTheDocument();
    act(() => vi.advanceTimersByTime(120000));
    rerender(<BoostStrip profile={{
      xp_boost_expires_at: '2026-10-16T12:10:00Z', xp_boost_seconds_remaining: 600,
    }} />);
    expect(screen.getByText('8m')).toBeInTheDocument();
  });

  it('counts an absolute expiry without a compatibility seconds field and removes the expired chip', () => {
    const { container } = render(<BoostStrip profile={{ drop_boost_expires_at: '2026-10-16T12:00:02Z' }} />);
    expect(screen.getByText('2s')).toBeInTheDocument();
    act(() => vi.advanceTimersByTime(2000));
    expect(container).toBeEmptyDOMElement();
  });

  it('falls back to relative seconds for an invalid expiry and removes the expired chip', () => {
    const { container } = render(<BoostStrip profile={{
      coin_boost_expires_at: 'invalid', coin_boost_seconds_remaining: 2,
    }} />);
    expect(screen.getByText('2s')).toBeInTheDocument();
    act(() => vi.advanceTimersByTime(2000));
    expect(container).toBeEmptyDOMElement();
  });
});
