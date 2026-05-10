import { describe, it, expect } from 'vitest';
import { renderWithProviders, screen } from '../../test/render';
import ChapterRubric from './ChapterRubric';

describe('ChapterRubric', () => {
  const subject = { name: 'Measuring & Layout', icon: '📐', summary: { level: 3, total_xp: 1200 } };

  it('renders the chapter numeral for its 0-based index', () => {
    renderWithProviders(<ChapterRubric index={0} subject={subject} />);
    expect(screen.getByText('§I')).toBeInTheDocument();
    renderWithProviders(<ChapterRubric index={2} subject={subject} />);
    expect(screen.getByText('§III')).toBeInTheDocument();
  });

  it('renders the subject name and icon', () => {
    renderWithProviders(<ChapterRubric index={0} subject={subject} />);
    expect(screen.getByText('Measuring & Layout')).toBeInTheDocument();
    expect(screen.getByText('📐')).toBeInTheDocument();
  });

  it('renders the subject summary when provided', () => {
    renderWithProviders(<ChapterRubric index={0} subject={subject} />);
    expect(screen.getByText(/L ?3/)).toBeInTheDocument();
    expect(screen.getByText(/1,?200\s*XP/i)).toBeInTheDocument();
  });

  it('is not a sticky element', () => {
    const { container } = renderWithProviders(<ChapterRubric index={0} subject={subject} />);
    const root = container.firstChild;
    expect(root.className).not.toContain('sticky');
    expect(root.className).not.toContain('top-0');
  });
});
