// Journal tokens only. The five raw Tailwind palette entries this map used to
// carry (emerald-400 / amber-400 / orange-400 / pink-400 / indigo-400) are
// pastels tuned for dark UIs — on the light parchment page they washed out to
// roughly 1.5:1 and the subject label read as a smudge. Every tone here is one
// of the six accent tokens the per-cover contrast gate already guards
// (test/themeContrast.test.js), so each chip stays legible on all six covers.
// Music reuses royal but wears the outlined shape so it stays distinct from
// writing.
const SUBJECT_COLORS = {
  math: 'bg-sheikah-teal/20 text-sheikah-teal-deep',
  reading: 'bg-moss/20 text-moss-deep',
  writing: 'bg-royal/20 text-royal',
  science: 'bg-gold-leaf/20 text-ember-deep',
  social_studies: 'bg-ember/20 text-ember-deep',
  art: 'bg-rose/20 text-rose',
  music: 'bg-royal/10 text-royal border border-royal/45',
  other: 'bg-ink-whisper/15 text-ink-secondary border border-ink-whisper/30',
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
    <span className={`inline-flex px-2 py-0.5 rounded-full text-caption font-medium ${color}`}>
      {label}
    </span>
  );
}
