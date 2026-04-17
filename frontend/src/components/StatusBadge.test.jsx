import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import StatusBadge from './StatusBadge.jsx';
import { STATUS_COLORS, STATUS_LABELS } from '../constants/colors.js';

describe('StatusBadge', () => {
  it('renders the mapped label for a known status', () => {
    const [key, label] = Object.entries(STATUS_LABELS)[0];
    render(<StatusBadge status={key} />);
    expect(screen.getByText(label)).toBeInTheDocument();
  });

  it('applies the mapped color class', () => {
    const [key, color] = Object.entries(STATUS_COLORS)[0];
    const { container } = render(<StatusBadge status={key} />);
    expect(container.firstChild.className).toContain(color.split(' ')[0]);
  });

  it('title-cases unknown statuses', () => {
    render(<StatusBadge status="weird" />);
    expect(screen.getByText('Weird')).toBeInTheDocument();
  });

  it('uses an ink-whisper token fallback for unknown statuses', () => {
    const { container } = render(<StatusBadge status="nope" />);
    // Token-driven fallback — no bg-gray-500 (which Tailwind 4 doesn't ship in this project's @theme)
    expect(container.firstChild.className).not.toContain('bg-gray');
    expect(container.firstChild.className).toContain('ink-whisper');
  });

  it('renders nothing visible for undefined status', () => {
    render(<StatusBadge status={undefined} />);
    // Should still render a span, even if the label is empty.
    const spans = document.querySelectorAll('span');
    expect(spans.length).toBeGreaterThan(0);
  });
});
