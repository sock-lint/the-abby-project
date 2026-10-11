import { describe, it, expect } from 'vitest';
import { renderWithProviders, screen } from '../../test/render';
import ChapterRubric from './ChapterRubric';

describe('ChapterRubric', () => {
  const subject = { name: 'Measuring & Layout', icon: '📐', summary: { level: 3, total_xp: 1200 } };

  it('renders the chapter numeral for its 0-based index', () => {
    renderWithProviders(<ChapterRubric index={0} subject={subject} />);
    expect(screen.getByText('1')).toHaveAttribute('data-chapter-marker', '1');
    renderWithProviders(<ChapterRubric index={2} subject={subject} />);
    expect(screen.getByText('3')).toHaveAttribute('data-chapter-marker', '3');
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

  it('accepts direct name/icon props for non-skill surfaces', () => {
    renderWithProviders(<ChapterRubric index={1} name="Hatch a New Pet" icon="🥚" />);
    expect(screen.getByText('2')).toHaveAttribute('data-chapter-marker', '2');
    expect(screen.getByText('Hatch a New Pet')).toBeInTheDocument();
    expect(screen.getByText('🥚')).toBeInTheDocument();
  });

  it('lets direct props override the legacy subject object', () => {
    renderWithProviders(
      <ChapterRubric index={0} subject={subject} name="Override Title" />,
    );
    expect(screen.getByText('Override Title')).toBeInTheDocument();
    expect(screen.queryByText('Measuring & Layout')).toBeNull();
  });
});
