import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import ApprovalButtons from './ApprovalButtons.jsx';

describe('ApprovalButtons', () => {
  it('renders default Approve/Reject labels', () => {
    render(<ApprovalButtons onApprove={() => {}} onReject={() => {}} />);
    expect(screen.getByRole('button', { name: /approve/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /reject/i })).toBeInTheDocument();
  });

  it('renders custom labels', () => {
    render(
      <ApprovalButtons
        onApprove={() => {}}
        onReject={() => {}}
        approveLabel="Yes"
        rejectLabel="No"
      />,
    );
    expect(screen.getByRole('button', { name: /yes/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /no/i })).toBeInTheDocument();
  });

  it('fires the correct callback for each button', async () => {
    const approve = vi.fn();
    const reject = vi.fn();
    const user = userEvent.setup();
    render(<ApprovalButtons onApprove={approve} onReject={reject} />);
    await user.click(screen.getByRole('button', { name: /approve/i }));
    await user.click(screen.getByRole('button', { name: /reject/i }));
    expect(approve).toHaveBeenCalledTimes(1);
    expect(reject).toHaveBeenCalledTimes(1);
  });
});
