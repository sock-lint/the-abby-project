import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { useState } from 'react';
import SelectField from './SelectField.jsx';

describe('SelectField', () => {
  it('associates the label with its custom combobox and opened options', async () => {
    const user = userEvent.setup();
    render(<SelectField label="Type"><option value="a">A</option><option value="b">B</option></SelectField>);
    const control = screen.getByRole('combobox', { name: 'Type' });
    expect(screen.getByLabelText('Type')).toBe(control);
    expect(control.tagName).toBe('BUTTON');
    await user.click(control);
    expect(screen.getByRole('listbox')).toHaveAttribute('id', control.getAttribute('aria-controls'));
    expect(screen.getAllByRole('option')).toHaveLength(2);
  });

  it('links help and errors without referencing hidden help', () => {
    const { rerender } = render(<SelectField label="Type" helpText="Pick one"><option>A</option></SelectField>);
    expect(screen.getByRole('combobox')).toHaveAccessibleDescription('Pick one');
    rerender(<SelectField label="Type" helpText="Pick one" error="Required"><option>A</option></SelectField>);
    expect(screen.getByRole('combobox')).toHaveAttribute('aria-invalid', 'true');
    expect(screen.getByRole('combobox')).toHaveAccessibleDescription('Required');
    expect(screen.getByRole('alert')).toHaveTextContent('Required');
    expect(screen.queryByText('Pick one')).not.toBeInTheDocument();
  });

  it('forwards controlled changes and displays the confirmed selected label', async () => {
    const user = userEvent.setup();
    function Harness() {
      const [value, setValue] = useState('a');
      return <SelectField label="Type" value={value} onChange={(event) => setValue(event.target.value)}><option value="a">A</option><option value="b">B</option></SelectField>;
    }
    render(<Harness />);
    await user.click(screen.getByLabelText('Type'));
    await user.click(screen.getByRole('option', { name: 'B' }));
    expect(screen.getByLabelText('Type')).toHaveValue('b');
    expect(screen.getByLabelText('Type')).toHaveTextContent('B');
  });

  it('supports an external label and compact filter variant', () => {
    render(<><label htmlFor="filter">Child</label><SelectField id="filter" variant="filter"><option>Everyone</option></SelectField></>);
    expect(screen.getByLabelText('Child')).toHaveValue('Everyone');
    expect(screen.getByRole('combobox')).toHaveClass('min-h-11', 'w-auto');
  });
});
