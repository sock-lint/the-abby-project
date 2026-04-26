import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Routes, Route, useLocation } from 'react-router-dom';
import VitalPipStrip from './VitalPipStrip.jsx';

function LocationProbe() {
  const loc = useLocation();
  return <div data-testid="loc">{loc.pathname}{loc.search}</div>;
}

function renderStrip(props = {}) {
  return render(
    <MemoryRouter initialEntries={['/dashboard']}>
      <Routes>
        <Route path="/dashboard" element={<><VitalPipStrip {...props} /><LocationProbe /></>} />
        <Route path="*" element={<LocationProbe />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe('VitalPipStrip', () => {
  it('renders coin/streak/level pips with values and aria labels', () => {
    renderStrip({ coinBalance: 42, loginStreak: 7, level: 3 });
    expect(screen.getByRole('button', { name: /42 coins/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /7-day streak/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /level 3/i })).toBeInTheDocument();
  });

  it('shows "no pet" when no active pet is provided', () => {
    renderStrip();
    expect(screen.getByRole('button', { name: /find a pet/i })).toBeInTheDocument();
  });

  it('coin pip navigates to /treasury?tab=bazaar', async () => {
    const user = userEvent.setup();
    renderStrip({ coinBalance: 10 });
    await user.click(screen.getByRole('button', { name: /10 coins/i }));
    expect(screen.getByTestId('loc')).toHaveTextContent('/treasury?tab=bazaar');
  });

  it('streak pip navigates to /sigil', async () => {
    const user = userEvent.setup();
    renderStrip({ loginStreak: 5 });
    await user.click(screen.getByRole('button', { name: /5-day streak/i }));
    expect(screen.getByTestId('loc')).toHaveTextContent('/sigil');
  });

  it('level pip navigates to /sigil', async () => {
    const user = userEvent.setup();
    renderStrip({ level: 2 });
    await user.click(screen.getByRole('button', { name: /level 2/i }));
    expect(screen.getByTestId('loc')).toHaveTextContent('/sigil');
  });

  it('pet pip navigates to /treasury?tab=satchel when no pet', async () => {
    const user = userEvent.setup();
    renderStrip();
    await user.click(screen.getByRole('button', { name: /find a pet/i }));
    expect(screen.getByTestId('loc')).toHaveTextContent('/treasury?tab=satchel');
  });

  it('pet pip navigates to /bestiary?tab=party when a pet is active', async () => {
    const user = userEvent.setup();
    renderStrip({
      activePet: { growth_points: 45, species: { name: 'Tortle', icon_url: null } },
    });
    await user.click(screen.getByRole('button', { name: /tortle growth/i }));
    expect(screen.getByTestId('loc')).toHaveTextContent('/bestiary?tab=party');
  });
});
