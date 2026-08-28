import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Routes, Route, useLocation } from 'react-router-dom';
import QuickAdjustRow from './QuickAdjustRow.jsx';

function LocationProbe() {
  const loc = useLocation();
  return <div data-testid="loc">{loc.pathname}{loc.search}</div>;
}

function renderRow() {
  return render(
    <MemoryRouter initialEntries={['/dashboard']}>
      <Routes>
        <Route path="/dashboard" element={<><QuickAdjustRow /><LocationProbe /></>} />
        <Route path="/treasury" element={<LocationProbe />} />
      </Routes>
    </MemoryRouter>,
  );
}

// Both adjusters live on Treasury — Bazaar holds the coin adjuster, Coffers
// the balance adjuster. They were pointed at /manage?tab=coins|payments, tabs
// Manage has never had, so every tap silently landed on Manage → Children.
describe('QuickAdjustRow', () => {
  it('renders both adjust buttons', () => {
    renderRow();
    expect(screen.getByRole('button', { name: /adjust coins/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /adjust payment/i })).toBeInTheDocument();
  });

  it('Adjust coins navigates to the Bazaar coin adjuster', async () => {
    const user = userEvent.setup();
    renderRow();
    await user.click(screen.getByRole('button', { name: /adjust coins/i }));
    expect(screen.getByTestId('loc')).toHaveTextContent('/treasury?tab=bazaar&adjust=1');
  });

  it('Adjust payment navigates to the Coffers balance adjuster', async () => {
    const user = userEvent.setup();
    renderRow();
    await user.click(screen.getByRole('button', { name: /adjust payment/i }));
    expect(screen.getByTestId('loc')).toHaveTextContent('/treasury?tab=coffers&adjust=1');
  });
});
