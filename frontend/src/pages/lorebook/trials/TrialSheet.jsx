import { useState } from 'react';
import { updateMe } from '../../../api';
import BottomSheet from '../../../components/BottomSheet';
import Button from '../../../components/Button';
import IlluminatedVersal from '../../achievements/IlluminatedVersal';
import { useAuth } from '../../../hooks/useApi';
import TapAndRewardTrial from './TapAndRewardTrial';
import ScribeTrial from './ScribeTrial';
import ObserveTrial from './ObserveTrial';
import ChoiceTrial from './ChoiceTrial';
import DragToTargetTrial from './DragToTargetTrial';
import SequenceTrial from './SequenceTrial';

const TEMPLATES = {
  tap_and_reward: TapAndRewardTrial,
  scribe: ScribeTrial,
  observe: ObserveTrial,
  choice: ChoiceTrial,
  drag_to_target: DragToTargetTrial,
  sequence: SequenceTrial,
};

export default function TrialSheet({ entry, onClose, onTrained }) {
  const { setUser } = useAuth();
  const [ready, setReady] = useState(false);
  const [saving, setSaving] = useState(false);

  if (!entry) return null;

  const Template = TEMPLATES[entry.trial_template];
  const slug = entry.slug;
  const letter = (entry.title || slug || '?').slice(0, 1);

  const handleInk = async () => {
    if (saving) return;
    setSaving(true);
    try {
      const nextUser = await updateMe({
        lorebook_flags: { [`${slug}_trained`]: true },
      });
      setUser?.(nextUser);
      onTrained?.(slug);
      onClose?.();
    } finally {
      setSaving(false);
    }
  };

  const handleClose = () => {
    if (saving) return;
    onClose?.();
  };

  return (
    <BottomSheet title={`Trial · ${entry.title}`} onClose={handleClose} disabled={saving}>
      <div className="space-y-4">
        <header className="flex items-center gap-3">
          <IlluminatedVersal letter={letter} size="md" tier="rising" progressPct={0} />
          <div className="min-w-0 flex-1">
            <div className="font-script text-caption text-sheikah-teal-deep leading-snug">
              apprentice trial
            </div>
            <div className="font-display italic text-lg text-ink-primary truncate">
              {entry.audience_title || entry.title}
            </div>
          </div>
        </header>

        <div
          aria-hidden="true"
          className="h-px bg-gradient-to-r from-transparent via-ink-page-shadow/70 to-transparent"
        />

        {Template ? (
          <Template entry={entry} onReady={() => setReady(true)} />
        ) : (
          <div className="text-sm italic text-ink-whisper text-center">
            This trial template hasn't been authored yet.
          </div>
        )}

        <Button
          onClick={handleInk}
          disabled={!ready || saving}
          className="w-full"
        >
          {saving ? 'Inking…' : 'Ink the page'}
        </Button>
        {!ready && (
          <p className="text-caption italic text-ink-whisper text-center">
            Finish the trial to ink this page into your Lorebook.
          </p>
        )}
      </div>
    </BottomSheet>
  );
}
