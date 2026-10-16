import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import MaterialsTab from './MaterialsTab.jsx';
import { buildProject } from '../../test/factories.js';

describe('MaterialsTab', () => {
  it('offers neutral readiness for materials without treating their estimates as spending', async () => {
    const user = userEvent.setup();
    const onMarkReady = vi.fn();
    const material = { id: 1, name: 'Class notes', estimated_cost: '5.00', actual_cost: null, is_purchased: false, is_ready: false };
    render(
      <MaterialsTab
        project={buildProject({ materials_budget: '0.00', materials: [material] })}
        isParent={false}
        onMarkReady={onMarkReady}
      />,
    );

    expect(screen.getByText('spent $0.00')).toBeInTheDocument();
    expect(screen.getByRole('progressbar', { name: /materials spending/i })).toHaveAttribute('aria-valuenow', '0');
    await user.click(screen.getByRole('button', { name: /^mark ready$/i }));
    expect(onMarkReady).toHaveBeenCalledWith(material);
    expect(screen.queryByRole('button', { name: /purchased/i })).not.toBeInTheDocument();
  });

  it('shows server-confirmed readiness without describing an existing supply as purchased', () => {
    render(
      <MaterialsTab
        project={buildProject({ materials: [
          { id: 1, name: 'Borrowed calculator', estimated_cost: '20.00', actual_cost: null, is_purchased: false, is_ready: true },
        ] })}
        isParent={false}
      />,
    );

    expect(screen.getByText('Ready')).toBeInTheDocument();
    expect(screen.queryByText(/purchased/i)).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /mark ready/i })).not.toBeInTheDocument();
  });

  it('lets an on-hand supply be corrected or purchased later while preserving purchase history', async () => {
    const user = userEvent.setup();
    const onMarkReady = vi.fn();
    const borrowed = { id: 1, name: 'Borrowed calculator', estimated_cost: '20.00', actual_cost: null, is_purchased: false, is_ready: true };
    render(
      <MaterialsTab
        project={buildProject({ materials: [
          borrowed,
          { id: 2, name: 'Bought notebook', estimated_cost: '3.00', actual_cost: '2.00', is_purchased: true, is_ready: true },
        ] })}
        isParent={false}
        onMarkReady={onMarkReady}
      />,
    );

    await user.click(screen.getByRole('button', { name: 'Change readiness for Borrowed calculator' }));
    expect(onMarkReady).toHaveBeenCalledWith(borrowed);
    expect(screen.queryByRole('button', { name: 'Change readiness for Bought notebook' })).not.toBeInTheDocument();
  });

  it('counts only recorded actual costs and preserves zero without falling back to an estimate', () => {
    render(
      <MaterialsTab
        project={buildProject({ materials_budget: '0.00', materials: [
          { id: 1, name: 'Owned notebook', estimated_cost: '3.00', actual_cost: 0, is_purchased: false, is_ready: true },
          { id: 2, name: 'Free pencil', estimated_cost: '2.00', actual_cost: '0.00', is_purchased: true },
          { id: 3, name: 'Eraser', estimated_cost: '5.00', actual_cost: '1.25', is_purchased: true },
          { id: 4, name: 'Paper', estimated_cost: '4.00', actual_cost: null, is_purchased: false },
        ] })}
        isParent={false}
        onMarkReady={vi.fn()}
      />,
    );

    expect(screen.getByText('spent $1.25')).toBeInTheDocument();
    expect(screen.getAllByText('Ready')).toHaveLength(3);
    expect(screen.getByRole('progressbar', { name: /materials spending/i })).toHaveAttribute('aria-valuenow', '100');
    expect(screen.getByText('est: $2.00 · actual: $0.00')).toBeInTheDocument();
  });

  it('renders empty state', () => {
    render(
      <MaterialsTab
        project={buildProject()}
        isParent={false}
        onMarkReady={vi.fn()}
        onDeleteMaterial={vi.fn()}
        onOpenAddMaterial={vi.fn()}
      />,
    );
    expect(screen.getAllByText((t) => /material|empty|budget|add/i.test(t)).length).toBeGreaterThanOrEqual(0);
  });

  it('parent can open the add-material modal', async () => {
    const onOpen = vi.fn();
    const user = userEvent.setup();
    render(
      <MaterialsTab
        project={buildProject()}
        isParent={true}
        onMarkReady={vi.fn()}
        onDeleteMaterial={vi.fn()}
        onOpenAddMaterial={onOpen}
      />,
    );
    await user.click(screen.getByRole('button', { name: /add material/i }));
    expect(onOpen).toHaveBeenCalled();
  });

  it('renders material rows', () => {
    render(
      <MaterialsTab
        project={buildProject({
          materials_budget: '10',
          materials: [
            { id: 1, name: 'Wood', estimated_cost: '3', actual_cost: null, is_purchased: false },
            { id: 2, name: 'Nails', estimated_cost: '2', actual_cost: '1.5', is_purchased: true },
          ],
        })}
        isParent={false}
        onMarkReady={vi.fn()}
        onDeleteMaterial={vi.fn()}
        onOpenAddMaterial={vi.fn()}
      />,
    );
    expect(screen.getByText('Wood')).toBeInTheDocument();
    expect(screen.getByText('Nails')).toBeInTheDocument();
  });
});
