import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import DailyExpeditionCard from './DailyExpeditionCard';

const mount = { id: 5, expedition_available: true, expedition_available_at: null, active_expedition: null };

describe('Daily expedition card', () => {
  it('opens duration choices without starting a trip', async () => {
    const user = userEvent.setup();
    const launch = vi.fn();
    const claim = vi.fn();
    render(<DailyExpeditionCard mount={mount} name="Peep" onLaunch={launch} onClaim={claim} />);
    expect(screen.getByText(/once a day/)).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Choose an expedition' }));
    expect(launch).toHaveBeenCalledExactlyOnceWith(mount);
    expect(claim).not.toHaveBeenCalled();
  });
  it('keeps an away pet unclaimable until the server reports its return', async () => {
    const user = userEvent.setup();
    const refresh = vi.fn();
    const claim = vi.fn();
    render(<DailyExpeditionCard mount={{ ...mount, expedition_available: false, active_expedition: { id: 33, status: 'active', is_ready: false, seconds_remaining: 90 } }} name="Peep" onRefresh={refresh} onClaim={claim} />);
    expect(screen.getByRole('heading', { name: 'Peep is exploring' })).toBeInTheDocument();
    expect(screen.getByText(/Back in 2m/)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Collect your finds' })).toBeNull();
    await user.click(screen.getByRole('button', { name: 'Check their return' }));
    expect(refresh).toHaveBeenCalledTimes(1);
    expect(claim).not.toHaveBeenCalled();
  });
  it('requires a deliberate collect click even for a returned trip', async () => {
    const user = userEvent.setup();
    const claim = vi.fn();
    render(<DailyExpeditionCard mount={{ ...mount, active_expedition: { id: 33, status: 'active', is_ready: true } }} name="Peep" onClaim={claim} />);
    expect(claim).not.toHaveBeenCalled();
    await user.click(screen.getByRole('button', { name: 'Collect your finds' }));
    expect(claim).toHaveBeenCalledExactlyOnceWith(33);
  });
  it('preserves play but offers no second launch when today’s expedition is complete', () => {
    render(<DailyExpeditionCard mount={{ ...mount, expedition_available: false, expedition_available_at: '2026-10-13T00:00:00-07:00' }} name="Peep" />);
    expect(screen.getByText(/Come back tomorrow/)).toHaveTextContent('you can still play together now');
    expect(screen.queryByRole('button', { name: 'Choose an expedition' })).toBeNull();
  });
  it('explains an unavailable appearance without claiming that this pet already traveled', () => {
    render(<DailyExpeditionCard mount={{ ...mount, expedition_available: false, expedition_available_at: null, expedition_available_in_seconds: null }} name="Frost" />);
    expect(screen.getByText(/Another appearance of this species has an expedition to finish/)).toBeInTheDocument();
    expect(screen.getByText(/All appearances of the same species share one expedition per day/)).toBeInTheDocument();
    expect(screen.queryByText(/Frost has explored/)).toBeNull();
    expect(screen.queryByRole('button', { name: 'Choose an expedition' })).toBeNull();
    expect(screen.queryByRole('button', { name: 'Collect your finds' })).toBeNull();
  });
  it('requests a server refresh instead of offering a trip when eligibility is unknown', async () => {
    const refresh = vi.fn();
    render(<DailyExpeditionCard mount={{ ...mount, expedition_available: undefined }} name="Frost" onRefresh={refresh} />);
    expect(screen.queryByRole('button', { name: 'Choose an expedition' })).toBeNull();
    await userEvent.setup().click(screen.getByRole('button', { name: 'Check availability' }));
    expect(refresh).toHaveBeenCalledTimes(1);
  });
});
