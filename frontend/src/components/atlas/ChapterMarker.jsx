import { chapterMark } from './mastery.constants';

// Quiet numbered waypoints shared by section headings and collection shelves.
// The adjacent heading names the section for assistive technology.
export default function ChapterMarker({ index, children, className = '' }) {
  const label = index != null ? chapterMark(index) : children;
  if (label == null || label === '') return null;

  return (
    <span
      aria-hidden="true"
      data-chapter-marker={label}
      className={`inline-flex items-center justify-center shrink-0 min-w-6 h-6 px-1.5 rounded-full bg-moss/15 text-moss-deep font-body font-bold text-caption leading-none tabular-nums select-none ${className}`}
    >
      {label}
    </span>
  );
}
