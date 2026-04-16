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

  it('uses the "other" color palette for unknown subjects', () => {
    const { container } = render(<SubjectBadge subject="mystery" />);
    expect(container.firstChild.className).toContain('bg-gray-500/20');
  });
});
