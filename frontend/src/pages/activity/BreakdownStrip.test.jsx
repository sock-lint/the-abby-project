import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import BreakdownStrip from './BreakdownStrip.jsx';

describe('BreakdownStrip', () => {
  it('returns nothing for an empty breakdown', () => {
    const { container } = render(<BreakdownStrip breakdown={[]} />);
    expect(container.firstChild).toBeNull();
  });

  it('renders each step with label and stringified value', () => {
    render(
      <BreakdownStrip
        breakdown={[
          { label: 'base', value: 5, op: '×' },
          { label: 'multiplier', value: 1.49, op: '=' },
          { label: 'coins awarded', value: 7, op: 'note' },
        ]}
      />,
    );
    expect(screen.getByText('base')).toBeInTheDocument();
    expect(screen.getByText('5')).toBeInTheDocument();
    expect(screen.getByText('multiplier')).toBeInTheDocument();
    expect(screen.getByText('1.49')).toBeInTheDocument();
    expect(screen.getByText('coins awarded')).toBeInTheDocument();
  });

  it('handles string values (for decimals coerced by the backend)', () => {
    render(
      <BreakdownStrip
        breakdown={[{ label: 'amount', value: '3.50', op: '=' }]}
      />,
    );
    expect(screen.getByText('3.50')).toBeInTheDocument();
  });
});
