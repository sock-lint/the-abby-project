import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { ArrowRight, X } from 'lucide-react';
import ParchmentCard from '../journal/ParchmentCard';
import IconButton from '../IconButton';
import SectionHeader from '../SectionHeader';

const STORAGE_KEY = 'onboarding-dismissed';

// These are optional destinations, not completion claims: the dashboard does
// not report whether the family's chores, rewards or projects are configured.
const SUGGESTIONS = [
  { key: 'chore', label: 'Set up chores', route: '/quests?tab=duties' },
  { key: 'reward', label: 'Set up the reward shop', route: '/treasury?tab=bazaar' },
  { key: 'project', label: 'Explore projects', route: '/quests?tab=ventures' },
];

export default function OnboardingChecklist({ data, user }) {
  const navigate = useNavigate();
  const storageKey = user?.id ? `${STORAGE_KEY}:${user.family?.id ?? ''}:${user.id}` : STORAGE_KEY;
  const [dismissedFor, setDismissedFor] = useState(null);
  let dismissed = dismissedFor === storageKey;
  try { dismissed ||= localStorage.getItem(storageKey) === 'true'; } catch { /* Storage is optional. */ }

  if (dismissed || !data) return null;

  const suggestions = data.children_count === 0
    ? [{ key: 'child', label: 'Add a child to your family', route: '/manage' }, ...SUGGESTIONS]
    : SUGGESTIONS;

  const handleDismiss = () => {
    try { localStorage.setItem(storageKey, 'true'); } catch { /* Storage is optional. */ }
    setDismissedFor(storageKey);
  };

  return (
    <ParchmentCard>
      <div className="flex items-start justify-between mb-3">
        <SectionHeader title="Getting started">
          Optional ways to set up your family&apos;s activities.
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
      {data.children_count > 0 && <p className="text-body text-ink-secondary mb-3">Children sign in with their own sign-in name and secret word, on their device or in a private browser window. Find their sign-in name under Manage → Children.</p>}
      <ul className="space-y-2">
        {suggestions.map((step) => (
          <li key={step.key}>
            <button
              type="button"
              onClick={() => navigate(step.route)}
              className="flex min-h-11 items-center gap-2.5 w-full text-left px-2 py-1.5 rounded-lg transition-colors text-ink-secondary hover:bg-ink-page/40 hover:text-ink-primary"
            >
              <ArrowRight size={18} className="shrink-0 text-sheikah-teal-deep" aria-hidden="true" />
              <span className="min-w-0 break-words text-caption font-body">
                {step.label}
              </span>
            </button>
          </li>
        ))}
      </ul>
    </ParchmentCard>
  );
}
