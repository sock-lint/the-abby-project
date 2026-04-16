import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import SealCloseButton from './SealCloseButton.jsx';

describe('SealCloseButton', () => {
  it('renders with default Close aria label', () => {
    render(<SealCloseButton onClick={() => {}} />);
    expect(screen.getByRole('button', { name: /close/i })).toBeInTheDocument();
  });

  it('accepts a custom aria-label', () => {
    render(<SealCloseButton onClick={() => {}} ariaLabel="Dismiss" />);
    expect(screen.getByRole('button', { name: 'Dismiss' })).toBeInTheDocument();
  });

  it('fires onClick', async () => {
    const onClick = vi.fn();
    const user = userEvent.setup();
    render(<SealCloseButton onClick={onClick} />);
    await user.click(screen.getByRole('button'));
    expect(onClick).toHaveBeenCalled();
  });

  it('respects disabled', () => {
    render(<SealCloseButton onClick={() => {}} disabled />);
    expect(screen.getByRole('button')).toBeDisabled();
  });

  it('applies ember gradient by default', () => {
    const { container } = render(<SealCloseButton onClick={() => {}} />);
    // jsdom normalizes hex colors to rgb(). #e88a5e → rgb(232, 138, 94).
    expect(container.querySelector('button').style.background).toContain('rgb(232, 138, 94)');
  });

  it('applies teal gradient when variant=teal', () => {
    const { container } = render(<SealCloseButton onClick={() => {}} variant="teal" />);
    // #4dd0e1 → rgb(77, 208, 225).
    expect(container.querySelector('button').style.background).toContain('rgb(77, 208, 225)');
  });
});
