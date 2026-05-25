import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { useState } from 'react';
import DateField from './DateField.jsx';

describe('DateField', () => {
  it('renders an <input type="date"> associated with its label', () => {
    render(<DateField label="From" />);
    const input = screen.getByLabelText('From');
    expect(input.tagName).toBe('INPUT');
    expect(input).toHaveAttribute('type', 'date');
  });

  it('forwards arbitrary props (min, max, name) to the underlying input', () => {
    render(<DateField label="From" name="start" min="2020-01-01" max="2030-12-31" />);
    const input = screen.getByLabelText('From');
    expect(input).toHaveAttribute('name', 'start');
    expect(input).toHaveAttribute('min', '2020-01-01');
    expect(input).toHaveAttribute('max', '2030-12-31');
  });

  it('renders helpText when provided', () => {
    render(<DateField label="From" helpText="ISO format" />);
    expect(screen.getByText('ISO format')).toBeInTheDocument();
  });

  it('renders error text and sets aria-invalid when error is provided', () => {
    render(<DateField label="From" error="Required" />);
    const input = screen.getByLabelText('From');
    expect(input).toHaveAttribute('aria-invalid', 'true');
    expect(screen.getByText('Required')).toBeInTheDocument();
  });

  it('is fully controlled — value updates on change', async () => {
    const user = userEvent.setup();
    function Harness() {
      const [v, setV] = useState('');
      return <DateField label="From" value={v} onChange={(e) => setV(e.target.value)} />;
    }
    render(<Harness />);
    const input = screen.getByLabelText('From');
    await user.type(input, '2026-05-24');
    expect(input).toHaveValue('2026-05-24');
  });

  it('applies the filter variant class when variant="filter"', () => {
    render(<DateField aria-label="From" variant="filter" />);
    const input = screen.getByLabelText('From');
    // Filter variant uses the compact toolbar styling, not the inputClass
    // wide-full default — pin on a class we know is filter-only.
    expect(input.className).toContain('w-auto');
    expect(input.className).toContain('text-caption');
  });

  it('omits the label element when label prop is missing', () => {
    const { container } = render(<DateField aria-label="From" />);
    expect(container.querySelector('label')).toBeNull();
    expect(container.querySelector('input[type="date"]')).toBeTruthy();
  });
});
