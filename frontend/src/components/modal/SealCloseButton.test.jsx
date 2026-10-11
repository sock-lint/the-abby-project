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

  it('keeps a 44px touch target with a decorative icon', () => {
    render(<SealCloseButton onClick={() => {}} />);
    const button = screen.getByRole('button', { name: 'Close' });
    expect(button).toHaveClass('min-h-11', 'min-w-11');
    expect(button.querySelector('svg')).toHaveAttribute('aria-hidden', 'true');
  });

  it('keeps the same accessible control for the teal variant', () => {
    render(<SealCloseButton onClick={() => {}} variant="teal" ariaLabel="Dismiss preview" />);
    expect(screen.getByRole('button', { name: 'Dismiss preview' })).toHaveAttribute('type', 'button');
  });
});
