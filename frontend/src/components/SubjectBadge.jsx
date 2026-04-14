const SUBJECT_COLORS = {
  math: 'bg-blue-500/20 text-sheikah-teal-deep',
  reading: 'bg-emerald-500/20 text-emerald-400',
  writing: 'bg-royal/20 text-royal',
  science: 'bg-amber-500/20 text-amber-400',
  social_studies: 'bg-orange-500/20 text-orange-400',
  art: 'bg-pink-500/20 text-pink-400',
  music: 'bg-indigo-500/20 text-indigo-400',
  other: 'bg-gray-500/20 text-gray-400',
};

const SUBJECT_LABELS = {
  math: 'Math',
  reading: 'Reading',
  writing: 'Writing',
  science: 'Science',
  social_studies: 'Social Studies',
  art: 'Art',
  music: 'Music',
  other: 'Other',
};

export default function SubjectBadge({ subject }) {
  const color = SUBJECT_COLORS[subject] || SUBJECT_COLORS.other;
  const label = SUBJECT_LABELS[subject] || subject;
  return (
    <span className={`inline-flex px-2 py-0.5 rounded-full text-xs font-medium ${color}`}>
      {label}
    </span>
  );
}
