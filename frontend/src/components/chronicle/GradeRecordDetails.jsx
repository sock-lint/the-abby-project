import { gradeResultText, reportCardPeriodText, reportCardSchoolYearText } from './gradeDisplay';

export default function GradeRecordDetails({ entry, showSubject = true }) {
  const report = entry.metadata?.report_card;
  if (report) {
    return (
      <div className="space-y-3">
        <dl className="grid grid-cols-2 gap-3 text-body">
          <div><dt className="text-caption text-ink-whisper">Reporting period</dt><dd>{reportCardPeriodText(report)}</dd></div>
          <div><dt className="text-caption text-ink-whisper">School year</dt><dd>{reportCardSchoolYearText(report)}</dd></div>
        </dl>
        <table className="w-full text-body table-fixed" aria-label="Report card grades">
          <thead><tr className="border-b border-ink-page-shadow text-left text-caption text-ink-whisper">
            <th scope="col" className="py-2 pr-3">Subject or class</th>
            <th scope="col" className="py-2">Recorded result</th>
          </tr></thead>
          <tbody>{(report.subjects ?? []).map((subject, index) => (
            <tr key={index} className="border-b border-ink-page-shadow">
              <th scope="row" className="py-2 pr-3 text-left font-semibold break-words">{subject.subject}</th>
              <td className="py-2 break-words">{gradeResultText({ metadata: { grade: subject } })}</td>
            </tr>
          ))}</tbody>
        </table>
      </div>
    );
  }
  const grade = entry.metadata?.grade;
  return (
    <dl className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-body">
      {showSubject && <div>
        <dt className="text-caption text-ink-whisper">Subject</dt>
        <dd className="font-semibold break-words">{grade?.subject || 'Not recorded'}</dd>
      </div>}
      <div>
        <dt className="text-caption text-ink-whisper">Assessment</dt>
        <dd className="break-words">{grade?.assessment || 'Not recorded'}</dd>
      </div>
      <div>
        <dt className="text-caption text-ink-whisper">Recorded result</dt>
        <dd className="font-serif text-lede break-words">{gradeResultText(entry)}</dd>
      </div>
    </dl>
  );
}
