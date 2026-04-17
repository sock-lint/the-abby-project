import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { useState } from 'react';
import TextField from './TextField.jsx';

describe('TextField', () => {
  it('associates the label with the input via htmlFor/id', () => {
    render(<TextField label="Name" />);
    const input = screen.getByLabelText('Name');
    expect(input.tagName).toBe('INPUT');
  });

  it('forwards arbitrary props to the underlying input', () => {
    render(<TextField label="Email" type="email" placeholder="you@x.com" />);
    const input = screen.getByLabelText('Email');
    expect(input).toHaveAttribute('type', 'email');
    expect(input).toHaveAttribute('placeholder', 'you@x.com');
  });

  it('renders helpText when provided', () => {
    render(<TextField label="Name" helpText="Use your full legal name" />);
    expect(screen.getByText('Use your full legal name')).toBeInTheDocument();
  });

  it('renders error text and sets aria-invalid when error is provided', () => {
    render(<TextField label="Name" error="Required" />);
    const input = screen.getByLabelText('Name');
    expect(input).toHaveAttribute('aria-invalid', 'true');
    expect(screen.getByText('Required')).toBeInTheDocument();
  });

  it('hides helpText when error is also provided', () => {
    render(<TextField label="Name" helpText="hint" error="bad" />);
    expect(screen.queryByText('hint')).not.toBeInTheDocument();
    expect(screen.getByText('bad')).toBeInTheDocument();
  });

  it('is fully controlled — value updates on each keystroke', async () => {
    const user = userEvent.setup();
    function Harness() {
      const [v, setV] = useState('');
      return <TextField label="Name" value={v} onChange={(e) => setV(e.target.value)} />;
    }
    render(<Harness />);
    await user.type(screen.getByLabelText('Name'), 'Abby');
    expect(screen.getByLabelText('Name')).toHaveValue('Abby');
  });

  it('omits the label element when label prop is missing', () => {
    const { container } = render(<TextField placeholder="just an input" />);
    expect(container.querySelector('label')).toBeNull();
    expect(container.querySelector('input')).toBeTruthy();
  });
});
