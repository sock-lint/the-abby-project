import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import TimelinessBadge from './TimelinessBadge.jsx';

describe('TimelinessBadge', () => {
  it.each([
    ['early', 'Early +25%'],
    ['on_time', 'On Time'],
    ['late', 'Late -50%'],
    ['beyond_cutoff', 'Past Cutoff'],
  ])('renders label for %s', (t, label) => {
    render(<TimelinessBadge timeliness={t} />);
    expect(screen.getByText(label)).toBeInTheDocument();
  });

  it('falls back to the raw value for unknown timeliness', () => {
    render(<TimelinessBadge timeliness="galactic" />);
    expect(screen.getByText('galactic')).toBeInTheDocument();
  });

  it('uses on_time styling for unknown timeliness', () => {
    const { container } = render(<TimelinessBadge timeliness="galactic" />);
    expect(container.firstChild.className).toContain('bg-blue-500/20');
  });
});
