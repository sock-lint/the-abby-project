import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import RuneBand from './RuneBand.jsx';

describe('RuneBand', () => {
  it('renders project title and elapsed label', () => {
    render(<RuneBand projectTitle="Arduino Bot" elapsedLabel="01:23" />);
    expect(screen.getByText('Arduino Bot')).toBeInTheDocument();
    expect(screen.getByText('01:23')).toBeInTheDocument();
  });

  it('renders fallback title when omitted', () => {
    render(<RuneBand elapsedLabel="00:00" />);
    expect(screen.getByText(/unclaimed venture/i)).toBeInTheDocument();
  });

  it('renders as a button when onClick is provided', async () => {
    const onClick = vi.fn();
    const user = userEvent.setup();
    render(<RuneBand projectTitle="x" elapsedLabel="00:00" onClick={onClick} />);
    await user.click(screen.getByRole('button'));
    expect(onClick).toHaveBeenCalled();
  });

  it('renders as a div when no onClick', () => {
    const { container } = render(<RuneBand projectTitle="x" elapsedLabel="00:00" />);
    expect(container.firstChild.tagName.toLowerCase()).toBe('div');
  });
});
