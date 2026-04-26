import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useFirstEncounter } from '../../hooks/useFirstEncounter';
import BottomSheet from '../BottomSheet';
import Button from '../Button';
import IlluminatedVersal from '../../pages/achievements/IlluminatedVersal';

export default function FirstEncounterSheet({ pollIntervalMs }) {
  const { activeEntry: entry, dismiss } = useFirstEncounter(pollIntervalMs);
  const [saving, setSaving] = useState(false);
  const navigate = useNavigate();

  if (!entry) return null;

  const handleDismiss = async () => {
    setSaving(true);
    try {
      await dismiss();
    } finally {
      setSaving(false);
    }
  };

  const handleTakeMeThere = async () => {
    setSaving(true);
    try {
      await dismiss();
      navigate(`/atlas?tab=lorebook&trial=${entry.slug}`);
    } finally {
      setSaving(false);
    }
  };

  const letter = (entry.title || entry.slug || '?').slice(0, 1);

  return (
    <BottomSheet title="A new page is open" onClose={handleDismiss} disabled={saving}>
      <div className="space-y-4 text-center">
        <div className="flex justify-center">
          <IlluminatedVersal letter={letter} size="lg" tier="rising" progressPct={0} />
        </div>
        <div className="space-y-1">
          <div className="font-script text-sheikah-teal-deep text-base">
            discovered · {entry.audience_title || entry.title}
          </div>
          <h2 className="font-display italic text-2xl text-ink-primary">
            {entry.title}
          </h2>
        </div>
        <p className="text-sm leading-relaxed text-ink-secondary">
          A new training awaits you in your Lorebook.
        </p>
        <div className="flex flex-col gap-2 pt-1">
          <Button onClick={handleTakeMeThere} disabled={saving} className="w-full">
            {saving ? 'Inking…' : 'Take me there'}
          </Button>
          <Button
            variant="ghost"
            onClick={handleDismiss}
            disabled={saving}
            className="w-full"
          >
            Later
          </Button>
        </div>
      </div>
    </BottomSheet>
  );
}
