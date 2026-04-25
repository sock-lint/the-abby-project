import { useState } from 'react';
import { useFirstEncounter } from '../../hooks/useFirstEncounter';
import BottomSheet from '../BottomSheet';
import Button from '../Button';

function firstParagraph(text = '') {
  return String(text).split(/\n\s*\n/).find(Boolean) || '';
}

export default function FirstEncounterSheet({ pollIntervalMs }) {
  const { activeEntry: entry, dismiss } = useFirstEncounter(pollIntervalMs);
  const [saving, setSaving] = useState(false);

  if (!entry) return null;

  const handleDismiss = async () => {
    setSaving(true);
    try {
      await dismiss();
    } finally {
      setSaving(false);
    }
  };

  return (
    <BottomSheet title="New Lorebook page" onClose={handleDismiss} disabled={saving}>
      <div className="space-y-4 text-center">
        <div className="text-5xl" aria-hidden="true">{entry.icon || '📖'}</div>
        <div>
          <div className="font-script text-sheikah-teal-deep text-base">
            discovered · {entry.audience_title || entry.title}
          </div>
          <h2 className="font-display italic text-2xl text-ink-primary">
            {entry.title}
          </h2>
        </div>
        <p className="text-sm leading-relaxed text-ink-secondary">
          {firstParagraph(entry.kid_voice) || entry.summary}
        </p>
        <p className="text-caption text-ink-whisper">
          This page is now open in your Atlas Lorebook.
        </p>
        <Button onClick={handleDismiss} disabled={saving} className="w-full">
          {saving ? 'Inking...' : 'Add it to my Lorebook'}
        </Button>
      </div>
    </BottomSheet>
  );
}
