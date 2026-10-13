import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import GradeRecordDetails from './GradeRecordDetails';

describe('GradeRecordDetails', () => {
  it('names the subject, assessment, and native result on a memory surface', () => {
    render(<GradeRecordDetails entry={{ metadata: { grade: {
      subject: 'Math', assessment: 'Fractions quiz', grade_format: 'points', score: '8', possible: '10',
    } } }} />);
    expect(screen.getByText('Math')).toBeInTheDocument();
    expect(screen.getByText('Fractions quiz')).toBeInTheDocument();
    expect(screen.getByText('8 / 10 points')).toBeInTheDocument();
    expect(screen.queryByText(/80%|GPA/)).toBeNull();
  });

  it('shows a report card period, school year and every subject in its recorded format', () => {
    render(<GradeRecordDetails entry={{ metadata: { report_card: {
      period_type: 'semester', period_number: 2, school_year: 2025,
      subjects: [
        { subject: 'Math', grade_format: 'letter', letter: 'A-' },
        { subject: 'Science', grade_format: 'percentage', score: '87.5' },
        { subject: 'Art', grade_format: 'points', score: '0', possible: '20' },
      ],
    } } }} />);
    expect(screen.getByText('Semester 2')).toBeInTheDocument();
    expect(screen.getByText('2025–2026')).toBeInTheDocument();
    expect(screen.getByRole('table', { name: 'Report card grades' })).toBeInTheDocument();
    for (const text of ['Math', 'A-', 'Science', '87.5%', 'Art', '0 / 20 points']) {
      expect(screen.getByText(text)).toBeInTheDocument();
    }
    expect(screen.queryByText(/Not recorded|Result unavailable|GPA/)).toBeNull();
  });
});
