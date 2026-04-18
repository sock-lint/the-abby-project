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
        <Route path="/manage" element={<LocationProbe />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe('QuickAdjustRow', () => {
  it('renders both adjust buttons', () => {
    renderRow();
    expect(screen.getByRole('button', { name: /adjust coins/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /adjust payment/i })).toBeInTheDocument();
  });

  it('Adjust coins navigates to /manage?tab=coins', async () => {
    const user = userEvent.setup();
    renderRow();
    await user.click(screen.getByRole('button', { name: /adjust coins/i }));
    expect(screen.getByTestId('loc')).toHaveTextContent('/manage?tab=coins');
  });

  it('Adjust payment navigates to /manage?tab=payments', async () => {
    const user = userEvent.setup();
    renderRow();
    await user.click(screen.getByRole('button', { name: /adjust payment/i }));
    expect(screen.getByTestId('loc')).toHaveTextContent('/manage?tab=payments');
  });
});
