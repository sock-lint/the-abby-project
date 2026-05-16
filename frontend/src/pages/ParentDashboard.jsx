import { Link } from 'react-router-dom';
import { UserPlus } from 'lucide-react';
import HeroPrimaryCard from '../components/dashboard/HeroPrimaryCard';
import ApprovalQueueList from '../components/dashboard/ApprovalQueueList';
import AccordionSection from '../components/dashboard/AccordionSection';
import WeekGlanceBlock from '../components/dashboard/WeekGlanceBlock';
import QuickAdjustRow from '../components/dashboard/QuickAdjustRow';
import ParchmentCard from '../components/journal/ParchmentCard';
import Button from '../components/Button';
import ErrorAlert from '../components/ErrorAlert';
import useParentDashboard from '../hooks/useParentDashboard';
import { inkBleed } from '../motion/variants';
import PageShell from '../components/layout/PageShell';
import { formatWeekdayDate } from './_dashboardShared';

function NoChildrenWelcome() {
  return (
    <ParchmentCard tone="bright">
      <div className="text-center py-6 px-4 space-y-3">
        <div className="mx-auto w-12 h-12 rounded-full bg-sheikah-teal/15 border border-sheikah-teal/40 flex items-center justify-center text-sheikah-teal-deep">
          <UserPlus size={22} />
        </div>
        <h2 className="font-display italic text-2xl text-ink-primary">
          Welcome — let&apos;s add your first kid.
        </h2>
        <p className="font-script text-ink-secondary max-w-md mx-auto text-body">
          Once a child is on the journal, you&apos;ll see their pending duties,
          studies, and rewards land here for one-tap approval.
        </p>
        <div className="pt-2">
          <Link to="/manage">
            <Button>Add a child</Button>
          </Link>
        </div>
      </div>
    </ParchmentCard>
  );
}

export default function ParentDashboard() {
  const { pending, weekByKid, dashboard, reload, failedSources = [] } = useParentDashboard();
  const { weekday, dateStr } = formatWeekdayDate();
  const failureMessage = failedSources.length > 0
    ? `Couldn't load ${failedSources.join(', ')} — pending items from those queues may be missing.`
    : null;

  // children_count is exposed by the parent dashboard payload. While the
  // dashboard request is in flight, treat it as "we don't know yet" and
  // fall back to whether any pending rows exist — that's enough to dodge
  // a flash of the empty-state on parents who already have kids.
  const childrenCount = dashboard?.children_count;
  const showWelcome = childrenCount === 0 && pending.length === 0;

  return (
    <PageShell variants={inkBleed}>
      <header>
        <div className="font-script text-sheikah-teal-deep text-base md:text-lg">
          {weekday} · {dateStr}
        </div>
        <h1 className="font-display italic text-3xl md:text-4xl text-ink-primary leading-tight">
          Today&apos;s Entry
        </h1>
      </header>

      {showWelcome ? (
        <NoChildrenWelcome />
      ) : (
        <>
          <HeroPrimaryCard
            role="parent"
            ctx={{
              weekday, dateStr,
              pendingCount: pending.length,
            }}
          />

          {failureMessage && (
            <div className="flex items-start gap-3">
              <ErrorAlert message={failureMessage} className="flex-1" />
              <Button variant="secondary" size="sm" onClick={reload}>
                Retry
              </Button>
            </div>
          )}

          <ApprovalQueueList items={pending} onDone={reload} />

          <AccordionSection
            index={0}
            title="Week at a glance"
            kicker="per-kid hours and earnings"
            peek={weekByKid.length > 0 ? `${weekByKid.length} kid${weekByKid.length !== 1 ? 's' : ''} active` : 'no week data yet'}
          >
            <WeekGlanceBlock weekByKid={weekByKid} />
          </AccordionSection>

          <AccordionSection
            index={1}
            title="Quick adjusts"
            kicker="manual ledger corrections"
            peek="Adjust coins · Adjust payment"
          >
            <QuickAdjustRow />
          </AccordionSection>
        </>
      )}
    </PageShell>
  );
}
