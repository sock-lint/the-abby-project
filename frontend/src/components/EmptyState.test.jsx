import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import EmptyState from './EmptyState.jsx';

describe('EmptyState', () => {
  it('renders children', () => {
    render(<EmptyState>No items yet</EmptyState>);
    expect(screen.getByText('No items yet')).toBeInTheDocument();
  });

  it('renders the icon prop when provided', () => {
    render(
      <EmptyState icon={<svg data-testid="ghost" />}>
        Nothing here
      </EmptyState>,
    );
    expect(screen.getByTestId('ghost')).toBeInTheDocument();
  });

  it('skips the icon slot when not provided', () => {
    const { container } = render(<EmptyState>Empty</EmptyState>);
    // The icon slot uses a `.flex.justify-center.mb-2` wrapper; the
    // ParchmentCard itself doesn't render that combination so its absence
    // is the signal.
    expect(container.querySelector('.justify-center.mb-2')).toBeNull();
  });

  it('accepts a custom className', () => {
    const { container } = render(
      <EmptyState className="custom">Empty</EmptyState>,
    );
    expect(container.firstChild.className).toContain('custom');
  });
});
