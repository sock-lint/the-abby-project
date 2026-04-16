import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import ErrorAlert from './ErrorAlert.jsx';

describe('ErrorAlert', () => {
  it('returns nothing when message is empty', () => {
    const { container } = render(<ErrorAlert message="" />);
    expect(container.firstChild).toBeNull();
  });

  it('returns nothing when message is null/undefined', () => {
    const { container: c1 } = render(<ErrorAlert message={null} />);
    const { container: c2 } = render(<ErrorAlert />);
    expect(c1.firstChild).toBeNull();
    expect(c2.firstChild).toBeNull();
  });

  it('renders the message when provided', () => {
    render(<ErrorAlert message="Boom!" />);
    expect(screen.getByText('Boom!')).toBeInTheDocument();
  });

  it('passes extra className through', () => {
    const { container } = render(<ErrorAlert message="x" className="mt-4" />);
    expect(container.firstChild.className).toContain('mt-4');
  });
});
