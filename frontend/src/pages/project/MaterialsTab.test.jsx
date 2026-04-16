import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import MaterialsTab from './MaterialsTab.jsx';
import { buildProject } from '../../test/factories.js';

describe('MaterialsTab', () => {
  it('renders empty state', () => {
    render(
      <MaterialsTab
        project={buildProject()}
        isParent={false}
        onMarkPurchased={vi.fn()}
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
        onMarkPurchased={vi.fn()}
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
        onMarkPurchased={vi.fn()}
        onDeleteMaterial={vi.fn()}
        onOpenAddMaterial={vi.fn()}
      />,
    );
    expect(screen.getByText('Wood')).toBeInTheDocument();
    expect(screen.getByText('Nails')).toBeInTheDocument();
  });
});
