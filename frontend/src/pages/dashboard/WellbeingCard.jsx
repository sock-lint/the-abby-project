import { Heart, PenTool } from 'lucide-react';
import { Link } from 'react-router-dom';
import ParchmentCard from '../../components/journal/ParchmentCard';
import Button from '../../components/Button';
import ErrorAlert from '../../components/ErrorAlert';
import { getWellbeingToday } from '../../api';
import { getToken } from '../../api/client';
import { useApi } from '../../hooks/useApi';
import { useRole } from '../../hooks/useRole';
import useJournalCapture from '../../hooks/useJournalCapture';
import JournalEntryFormModal from '../yearbook/JournalEntryFormModal';

/** Today's affirmation and a quick entrance to the same journal as Memories. */
export default function WellbeingCard() {
  const { user, isChild } = useRole();
  if (!user?.id || !isChild) return null;
  return <TodayJournalCard key={`${user.id}:${getToken()}`} />;
}

function TodayJournalCard() {
  const { data } = useApi(getWellbeingToday);
  const journal = useJournalCapture();
  const entry = journal.data?.id ? journal.data : null;

  return (
    <ParchmentCard tone="default" className="space-y-4">
      <header className="flex items-start gap-3">
        <Heart size={18} className="text-rose mt-1" aria-hidden="true" />
        <div>
          <p className="font-body text-caption text-royal">Your journal</p>
          <h2 className="font-body font-bold text-lg text-ink-primary">For you, today</h2>
        </div>
      </header>
      {data?.affirmation?.text && (
        <blockquote className="font-script text-lede text-ink-primary leading-snug border-l-2 border-gold-leaf/60 pl-3 italic" aria-label="today's affirmation">
          {data.affirmation.text}
        </blockquote>
      )}
      <p className="text-body text-ink-secondary">Write about anything, even a hard day. A few words count.</p>
      {entry && (
        <div className="rounded-xl bg-ink-page p-3 space-y-1" aria-label="Today’s saved journal entry">
          <p className="text-caption text-ink-secondary">Saved in your journal · {entry.is_private === false ? 'Shared with parents' : 'Only me'}</p>
          {entry.title && <h3 className="font-semibold text-body">{entry.title}</h3>}
          {entry.summary && <p className="whitespace-pre-wrap break-words text-body text-ink-primary line-clamp-3">{entry.summary}</p>}
        </div>
      )}
      <ErrorAlert message={journal.error} onRetry={journal.reload} />
      {!journal.error && (
        <Button variant="primary" onClick={journal.open} disabled={journal.loading || journal.refreshing} className="inline-flex items-center gap-2">
          <PenTool size={16} aria-hidden="true" />
          {journal.loading || journal.refreshing ? 'Checking today’s entry…' : entry ? 'Edit today’s entry' : 'Write today’s entry'}
        </Button>
      )}
      <p className="text-caption text-ink-secondary">The first new entry each day can earn writing XP and a 2 Coin daily bonus, alongside normal journal progress. Updates give no extra reward. Skipping a day has no penalty.</p>
      <p className="text-caption text-ink-secondary">Find all your entries in <Link to="/chronicle?tab=journal" className="underline text-royal">Memories → Journal</Link>.</p>
      {journal.capture && <JournalEntryFormModal {...journal.capture} onClose={journal.close} onSaved={journal.saved} />}
    </ParchmentCard>
  );
}
