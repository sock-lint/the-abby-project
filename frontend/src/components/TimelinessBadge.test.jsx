import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import TimelinessBadge from './TimelinessBadge.jsx';

describe('TimelinessBadge', () => {
  it.each([
    ['early', 'Early'],
    ['on_time', 'On time'],
    ['late', 'Late'],
    ['beyond_cutoff', 'Late'],
  ])('renders label for %s', (t, label) => {
    render(<TimelinessBadge timeliness={t} />);
    expect(screen.getByText(label)).toBeInTheDocument();
  });

  it.each([undefined, null, 'galactic', '__proto__'])('shows neutral unknown timing for %s without implying on-time work', (timeliness) => {
    render(<TimelinessBadge timeliness={timeliness} />);
    const badge = screen.getByText('Timing unknown');
    expect(badge).toHaveClass('text-ink-secondary');
    expect(badge).not.toHaveClass('text-sheikah-teal-deep');
    expect(screen.queryByText('On time')).not.toBeInTheDocument();
  });

  it('does not promise reward percentage changes from a submission classification', () => {
    const { container } = render(<TimelinessBadge timeliness="early" />);
    expect(container).not.toHaveTextContent('%');
  });
});
