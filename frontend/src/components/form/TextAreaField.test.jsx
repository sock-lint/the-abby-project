import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { useState } from 'react';
import TextAreaField from './TextAreaField.jsx';

describe('TextAreaField', () => {
  it('associates the label with the textarea', () => {
    render(<TextAreaField label="Notes" rows={5} />);
    const ta = screen.getByLabelText('Notes');
    expect(ta.tagName).toBe('TEXTAREA');
    expect(ta).toHaveAttribute('rows', '5');
  });

  it('defaults rows to 3', () => {
    render(<TextAreaField label="Notes" />);
    expect(screen.getByLabelText('Notes')).toHaveAttribute('rows', '3');
  });

  it('updates value via controlled change', async () => {
    const user = userEvent.setup();
    function Harness() {
      const [v, setV] = useState('');
      return <TextAreaField label="Notes" value={v} onChange={(e) => setV(e.target.value)} />;
    }
    render(<Harness />);
    await user.type(screen.getByLabelText('Notes'), 'Hello');
    expect(screen.getByLabelText('Notes')).toHaveValue('Hello');
  });

  it('renders helpText when provided', () => {
    render(<TextAreaField label="Notes" helpText="Markdown OK" />);
    expect(screen.getByText('Markdown OK')).toBeInTheDocument();
  });

  it('renders error and sets aria-invalid', () => {
    render(<TextAreaField label="Notes" error="Too short" />);
    expect(screen.getByLabelText('Notes')).toHaveAttribute('aria-invalid', 'true');
    expect(screen.getByText('Too short')).toBeInTheDocument();
  });

  it('hides helpText when error is also provided', () => {
    render(<TextAreaField label="Notes" helpText="hint" error="bad" />);
    expect(screen.queryByText('hint')).not.toBeInTheDocument();
    expect(screen.getByText('bad')).toBeInTheDocument();
  });
});
