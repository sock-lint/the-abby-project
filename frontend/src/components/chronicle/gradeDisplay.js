// Keep each result in the format it was recorded. A points result is never
// converted to a percentage, letter, or GPA on the memory surfaces.
export function gradeResultText(entry) {
  const report = entry.metadata?.report_card;
  if (report) {
    const count = report.subjects?.length ?? 0;
    return `${count} subject grade${count === 1 ? '' : 's'}`;
  }
  const grade = entry.metadata?.grade;
  if (!grade) return 'Result unavailable';
  if (grade.grade_format === 'percentage' && grade.score !== undefined && grade.score !== null) {
    return `${grade.score}%`;
  }
  if (grade.grade_format === 'points' && grade.score !== undefined && grade.score !== null
      && grade.possible !== undefined && grade.possible !== null) {
    return `${grade.score} / ${grade.possible} points`;
  }
  if (grade.grade_format === 'letter' && grade.letter) return grade.letter;
  return 'Result unavailable';
}

export function reportCardPeriodText(report) {
  return `${report.period_type === 'semester' ? 'Semester' : 'Quarter'} ${report.period_number}`;
}

export function reportCardSchoolYearText(report) {
  return `${report.school_year}–${Number(report.school_year) + 1}`;
}
