import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, fireEvent, render, screen } from '@testing-library/react';
import IncubationCard from './IncubationCard';

beforeEach(() => vi.useFakeTimers());
afterEach(() => { vi.useRealTimers(); vi.restoreAllMocks(); });

describe('Incubating egg presentation', () => {
  const egg = { name: 'Bat Egg', icon: '🥚' };

  it('keeps the 24-hour egg incubating after two hours and waits for server readiness at its deadline', () => {
    let elapsed = 0;
    vi.spyOn(performance, 'now').mockImplementation(() => elapsed);
    const onHatch = vi.fn();
    const view = render(<IncubationCard egg={egg} remainingSeconds={86400} isReady={false} onHatch={onHatch} onRefresh={() => {}} />);
    expect(screen.getByText('Ready to hatch in 24h.')).toBeInTheDocument();
    act(() => { elapsed = 7200000; vi.advanceTimersByTime(1000); });
    expect(screen.getByText('Ready to hatch in 22h.')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Hatch pet' })).toBeNull();
    act(() => { elapsed = 86400000; vi.advanceTimersByTime(1000); });
    expect(screen.getByText('Checking whether your egg is ready…')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Hatch pet' })).toBeNull();
    expect(onHatch).not.toHaveBeenCalled();
    view.rerender(<IncubationCard egg={egg} remainingSeconds={0} isReady onHatch={onHatch} onRefresh={() => {}} />);
    fireEvent.click(screen.getByRole('button', { name: 'Hatch pet' }));
    expect(onHatch).toHaveBeenCalledTimes(1);
  });

  it('counts down from server seconds without making an egg ready when the phone clock changes', () => {
    let elapsed = 0;
    vi.spyOn(performance, 'now').mockImplementation(() => elapsed);
    const onHatch = vi.fn(), onRefresh = vi.fn();
    render(<IncubationCard egg={egg} remainingSeconds={61} isReady={false} onHatch={onHatch} onRefresh={onRefresh} />);
    expect(screen.getByText(/Ready to hatch in 2m/)).toBeInTheDocument();
    vi.setSystemTime(new Date('2040-01-01T00:00:00Z'));
    act(() => { elapsed = 2000; vi.advanceTimersByTime(1000); });
    expect(screen.getByText(/Ready to hatch in 1m/)).toBeInTheDocument();
    act(() => { elapsed = 62000; vi.advanceTimersByTime(1000); });
    expect(screen.getByText(/Checking whether your egg is ready/)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Hatch pet' })).toBeNull();
    expect(onHatch).not.toHaveBeenCalled();
    expect(onRefresh).not.toHaveBeenCalled();
  });

  it('requires an explicit hatch click after the server confirms readiness', () => {
    const onHatch = vi.fn();
    render(<IncubationCard egg={egg} remainingSeconds={0} isReady onHatch={onHatch} onRefresh={() => {}} />);
    expect(screen.getByRole('heading', { name: 'Your egg is ready to hatch' })).toBeInTheDocument();
    expect(onHatch).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: 'Hatch pet' }));
    expect(onHatch).toHaveBeenCalledTimes(1);
  });

  it('keeps waiting and ready controls disabled while a save is in progress', () => {
    const view = render(<IncubationCard egg={egg} remainingSeconds={7200} isReady={false} working onRefresh={() => {}} />);
    expect(screen.getByRole('button', { name: 'Check readiness' })).toBeDisabled();
    view.rerender(<IncubationCard egg={egg} remainingSeconds={0} isReady working onHatch={() => {}} />);
    expect(screen.getByRole('button', { name: 'Hatching…' })).toBeDisabled();
  });
});
