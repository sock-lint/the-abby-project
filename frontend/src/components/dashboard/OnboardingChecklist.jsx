import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { CheckCircle2, Circle, X, BookOpen } from 'lucide-react';
import ParchmentCard from '../journal/ParchmentCard';
import IconButton from '../IconButton';
import SectionHeader from '../SectionHeader';

const STORAGE_KEY = 'onboarding-dismissed';

const STEPS = [
  { key: 'child', label: 'Add a child to your family', route: '/manage', check: (d) => (d._parent_extras?.children_count || 0) > 0 },
  { key: 'chore', label: 'Create a duty', route: '/quests?tab=duties', check: (d) => d._parent_extras?.has_chores },
  { key: 'reward', label: 'Set up a reward in the bazaar', route: '/treasury?tab=bazaar', check: (d) => d._parent_extras?.has_rewards },
  { key: 'project', label: 'Start a venture', route: '/quests?tab=ventures', check: (d) => (d.active_projects?.length || 0) > 0 },
];

export default function OnboardingChecklist({ data }) {
  const navigate = useNavigate();
  const [dismissed, setDismissed] = useState(
    () => localStorage.getItem(STORAGE_KEY) === 'true',
  );

  if (dismissed || !data) return null;

  const done = STEPS.filter((s) => s.check(data)).length;
  if (done === STEPS.length) return null;

  const handleDismiss = () => {
    localStorage.setItem(STORAGE_KEY, 'true');
    setDismissed(true);
  };

  return (
    <ParchmentCard tone="bright">
      <div className="flex items-start justify-between mb-3">
        <SectionHeader
          as="h3"
          icon={<BookOpen size={18} />}
        >
          Getting started
        </SectionHeader>
        <IconButton
          variant="ghost"
          size="sm"
          aria-label="Dismiss checklist"
          onClick={handleDismiss}
        >
          <X size={16} />
        </IconButton>
      </div>
      <ul className="space-y-2">
        {STEPS.map((step) => {
          const complete = step.check(data);
          return (
            <li key={step.key}>
              <button
                type="button"
                onClick={() => !complete && navigate(step.route)}
                disabled={complete}
                className={`flex items-center gap-2.5 w-full text-left px-2 py-1.5 rounded-lg transition-colors ${
                  complete
                    ? 'text-moss cursor-default'
                    : 'text-ink-secondary hover:bg-ink-page/40 hover:text-ink-primary'
                }`}
              >
                {complete ? (
                  <CheckCircle2 size={18} className="shrink-0 text-moss" />
                ) : (
                  <Circle size={18} className="shrink-0 text-ink-whisper" />
                )}
                <span className={`text-caption font-body ${complete ? 'line-through' : ''}`}>
                  {step.label}
                </span>
              </button>
            </li>
          );
        })}
      </ul>
      <p className="text-tiny text-ink-whisper mt-3 font-script italic">
        {done} of {STEPS.length} complete
      </p>
    </ParchmentCard>
  );
}
