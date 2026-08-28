import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import SubjectBadge from './SubjectBadge.jsx';

describe('SubjectBadge', () => {
  it('renders known subject labels', () => {
    render(<SubjectBadge subject="math" />);
    expect(screen.getByText('Math')).toBeInTheDocument();
  });

  it('handles social_studies label translation', () => {
    render(<SubjectBadge subject="social_studies" />);
    expect(screen.getByText('Social Studies')).toBeInTheDocument();
  });

  it('falls back to the raw subject for unknown keys', () => {
    render(<SubjectBadge subject="philosophy" />);
    expect(screen.getByText('philosophy')).toBeInTheDocument();
  });

  it('paints every subject in journal tokens, never dark-UI Tailwind pastels', () => {
    // reading/science/social_studies/art/music used to wear emerald-400 /
    // amber-400 / orange-400 / pink-400 / indigo-400 — pastels tuned for dark
    // backgrounds that washed out to an unreadable smudge on parchment.
    const subjects = [
      'math', 'reading', 'writing', 'science',
      'social_studies', 'art', 'music', 'other',
    ];
    for (const subject of subjects) {
      const { container, unmount } = render(<SubjectBadge subject={subject} />);
      const chip = container.firstChild;
      expect(chip.className, `${subject} chip`).not.toMatch(
        /(emerald|amber|orange|pink|indigo|blue|gray|slate|zinc)-\d{3}/,
      );
      unmount();
    }
  });

  it('uses the "other" color palette for unknown subjects', () => {
    const { container } = render(<SubjectBadge subject="mystery" />);
    // Token-driven fallback (was bg-gray-500/20, which Tailwind 4 doesn't ship in this project's @theme)
    expect(container.firstChild.className).toContain('ink-whisper');
    expect(container.firstChild.className).not.toContain('bg-gray');
  });
});
