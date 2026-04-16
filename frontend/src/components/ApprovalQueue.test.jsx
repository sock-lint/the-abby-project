import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import ApprovalQueue from './ApprovalQueue.jsx';

describe('ApprovalQueue', () => {
  it('renders nothing when items is empty and no emptyText', () => {
    const { container } = render(
      <ApprovalQueue items={[]} onApprove={() => {}} onReject={() => {}}>
        {() => <div />}
      </ApprovalQueue>,
    );
    expect(container.firstChild).toBeNull();
  });

  it('renders emptyText when items is empty and emptyText is set', () => {
    render(
      <ApprovalQueue
        items={[]}
        title="Pending Chores"
        emptyText="Nothing to review"
        onApprove={() => {}}
        onReject={() => {}}
      >
        {() => <div />}
      </ApprovalQueue>,
    );
    expect(screen.getByText('Nothing to review')).toBeInTheDocument();
    expect(screen.getByText('Pending Chores')).toBeInTheDocument();
  });

  it('renders items via the render-prop children', () => {
    const items = [
      { id: 1, name: 'Alpha' },
      { id: 2, name: 'Beta' },
    ];
    render(
      <ApprovalQueue items={items} title="Queue" onApprove={() => {}} onReject={() => {}}>
        {({ item, actions }) => (
          <div key={item.id}>
            <span>{item.name}</span>
            {actions}
          </div>
        )}
      </ApprovalQueue>,
    );
    expect(screen.getByText('Alpha')).toBeInTheDocument();
    expect(screen.getByText('Beta')).toBeInTheDocument();
  });

  it('wires onApprove/onReject with each item id', async () => {
    const approve = vi.fn();
    const reject = vi.fn();
    const user = userEvent.setup();
    render(
      <ApprovalQueue
        items={[{ id: 42, name: 'x' }]}
        onApprove={approve}
        onReject={reject}
      >
        {({ item, actions }) => (
          <div key={item.id}>
            <span>{item.name}</span>
            {actions}
          </div>
        )}
      </ApprovalQueue>,
    );
    await user.click(screen.getByRole('button', { name: /approve/i }));
    await user.click(screen.getByRole('button', { name: /reject/i }));
    expect(approve).toHaveBeenCalledWith(42);
    expect(reject).toHaveBeenCalledWith(42);
  });

  it('renders header with icon', () => {
    render(
      <ApprovalQueue
        items={[]}
        icon={<svg data-testid="icn" />}
        emptyText="empty"
        onApprove={() => {}}
        onReject={() => {}}
      >
        {() => null}
      </ApprovalQueue>,
    );
    expect(screen.getByTestId('icn')).toBeInTheDocument();
  });

  it('omits the header when neither title nor icon is given', () => {
    const { container } = render(
      <ApprovalQueue
        items={[{ id: 1 }]}
        onApprove={() => {}}
        onReject={() => {}}
      >
        {({ item }) => <div key={item.id}>row</div>}
      </ApprovalQueue>,
    );
    expect(container.querySelector('h2')).toBeNull();
  });
});
