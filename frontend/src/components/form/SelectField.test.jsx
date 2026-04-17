import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { useState } from 'react';
import SelectField from './SelectField.jsx';

describe('SelectField', () => {
  it('associates the label with the select via htmlFor/id', () => {
    render(
      <SelectField label="Type">
        <option value="a">A</option>
        <option value="b">B</option>
      </SelectField>,
    );
    const select = screen.getByLabelText('Type');
    expect(select.tagName).toBe('SELECT');
    expect(select.querySelectorAll('option')).toHaveLength(2);
  });

  it('renders helpText when provided', () => {
    render(
      <SelectField label="Type" helpText="Pick one">
        <option value="a">A</option>
      </SelectField>,
    );
    expect(screen.getByText('Pick one')).toBeInTheDocument();
  });

  it('renders error and sets aria-invalid when error is provided', () => {
    render(
      <SelectField label="Type" error="Required">
        <option value="">--</option>
      </SelectField>,
    );
    expect(screen.getByLabelText('Type')).toHaveAttribute('aria-invalid', 'true');
    expect(screen.getByText('Required')).toBeInTheDocument();
  });

  it('hides helpText when error is also provided', () => {
    render(
      <SelectField label="Type" helpText="hint" error="bad">
        <option value="">--</option>
      </SelectField>,
    );
    expect(screen.queryByText('hint')).not.toBeInTheDocument();
    expect(screen.getByText('bad')).toBeInTheDocument();
  });

  it('forwards value/onChange (controlled)', async () => {
    const user = userEvent.setup();
    function Harness() {
      const [v, setV] = useState('a');
      return (
        <SelectField label="Type" value={v} onChange={(e) => setV(e.target.value)}>
          <option value="a">A</option>
          <option value="b">B</option>
        </SelectField>
      );
    }
    render(<Harness />);
    await user.selectOptions(screen.getByLabelText('Type'), 'b');
    expect(screen.getByLabelText('Type')).toHaveValue('b');
  });

  it('omits the label element when label prop is missing', () => {
    const { container } = render(
      <SelectField>
        <option value="a">A</option>
      </SelectField>,
    );
    expect(container.querySelector('label')).toBeNull();
    expect(container.querySelector('select')).toBeTruthy();
  });
});
