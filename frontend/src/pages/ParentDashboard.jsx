import { Link, useNavigate } from 'react-router-dom';
import { UserPlus, CalendarDays, Settings2 } from 'lucide-react';
import HeroPrimaryCard from '../components/dashboard/HeroPrimaryCard';
import OnboardingChecklist from '../components/dashboard/OnboardingChecklist';
import ApprovalQueueList from '../components/dashboard/ApprovalQueueList';
import AccordionSection from '../components/dashboard/AccordionSection';
import QuickAdjustRow from '../components/dashboard/QuickAdjustRow';
import ParchmentCard from '../components/journal/ParchmentCard';
import Button from '../components/Button';
import ErrorAlert from '../components/ErrorAlert';
import SectionHeader from '../components/SectionHeader';
import { getChildren } from '../api';
import { useApi } from '../hooks/useApi';
import useParentDashboard from '../hooks/useParentDashboard';
import { inkBleed } from '../motion/variants';
import PageShell from '../components/layout/PageShell';
import PageHeader from '../components/layout/PageHeader';
import { formatCurrency } from '../utils/format';
import { normalizeList } from '../utils/api';
import { formatWeekdayDate } from './_dashboardShared';

function NoChildrenWelcome() {
  return (
    <ParchmentCard tone="bright">
      <div className="text-center py-6 px-4 space-y-3">
        <div className="mx-auto w-12 h-12 rounded-full bg-sheikah-teal/15 border border-sheikah-teal/40 flex items-center justify-center text-sheikah-teal-deep">
          <UserPlus size={22} />
        </div>
        <h2 className="font-body font-bold text-2xl text-ink-primary">
          Welcome — let&apos;s add your first kid.
        </h2>
        <p className="font-script text-ink-secondary max-w-md mx-auto text-body">
          Add a child to see their projects, study, and rewards here.
          You can encourage their progress and review what needs approval.
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
  const {
    pending, weekByKid, dashboard, reload, loading, failedSources = [], error,
  } = useParentDashboard();
  const {
    data: childrenData, loading: childrenLoading, error: childrenError, reload: reloadChildren,
  } = useApi(getChildren);
  const children = normalizeList(childrenData);
  const navigate = useNavigate();
  const { weekday, dateStr } = formatWeekdayDate();
  const failureMessage = failedSources.length > 0
    ? `Couldn't load ${failedSources.join(', ')} — pending items from those queues may be missing.`
    : error;
  const incomplete = Boolean(failureMessage);
  const pendingTimecards = Number(dashboard?.pending_timecards) || 0;
  const attentionCount = pending.length + pendingTimecards;
  const weekUnavailable = failedSources.includes('week summary');

  // children_count is exposed by the parent dashboard payload. While the
  // dashboard request is in flight, treat the family size as unknown.
  const childrenCount = dashboard?.children_count;
  const showWelcome = childrenCount === 0 && attentionCount === 0;

  return (
    <PageShell variants={inkBleed}>
      <PageHeader
        title="Today"
        kicker={`${weekday} · ${dateStr} · your family's day at a glance`}
      />

      {failureMessage && (
        <div className="flex flex-col sm:flex-row sm:items-start gap-3">
          <ErrorAlert message={failureMessage} className="flex-1" />
          <Button variant="secondary" size="sm" onClick={reload} className="self-end sm:self-auto">
            Retry
          </Button>
        </div>
      )}

      {showWelcome ? (
        <NoChildrenWelcome />
      ) : (
        <>
          <HeroPrimaryCard
            role="parent"
            ctx={{
              weekday, dateStr,
              pendingCount: attentionCount,
              loading,
              incomplete,
              hideDate: true,
            }}
          />

          {/* `loading` is load-bearing: the queue aggregates eight fetches, and
              without it the list renders "No pending approvals. All quiet" for
              the whole multi-second round trip — a glance-and-leave parent
              reads that as an all-clear and misses the queue entirely. */}
          <section id="approval-queue" aria-label="Needs your attention" className="space-y-3 scroll-mt-28">
            {pendingTimecards > 0 && (
              <ParchmentCard>
                <Link
                  to="/treasury?tab=wages"
                  className="flex min-h-11 items-center gap-3 text-sheikah-teal-deep font-body font-semibold text-body hover:underline"
                >
                  <CalendarDays size={20} className="shrink-0" aria-hidden="true" />
                  Review {pendingTimecards} timecard{pendingTimecards !== 1 ? 's' : ''}
                </Link>
              </ParchmentCard>
            )}
            <ApprovalQueueList
              items={pending}
              loading={loading}
              incomplete={incomplete}
              showEmpty={pendingTimecards === 0}
              onDone={reload}
            />
          </section>

          <section aria-label="Family overview" className="space-y-3">
            <SectionHeader title="Family overview" kicker="Clocked activity this week" />
            {childrenLoading ? (
              <p className="font-body text-caption text-ink-secondary">Loading...</p>
            ) : childrenError ? (
              <ErrorAlert message="Couldn't load your family. Please try again." onRetry={reloadChildren} />
            ) : children.length > 0 ? (
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                {children.map((child) => {
                  const kidWeek = weekByKid.find((w) => w.kid_id === child.id);
                  const name = child.display_name || child.username;
                  return (
                    // Button OUTSIDE the card (the Next Up pattern on
                    // ChildDashboard) so the whole tile is the tap target and
                    // the card pads once instead of p-5 + px-3 py-3.
                    <button
                      key={child.id}
                      type="button"
                      onClick={() => navigate('/manage')}
                      aria-label={`Manage ${name}`}
                      className="min-w-0 text-left"
                    >
                      <ParchmentCard className="h-full space-y-1">
                        <span className="font-display text-body text-ink-primary block break-words [overflow-wrap:anywhere]">
                          {name}
                        </span>
                        <span className="font-body text-caption text-ink-secondary block">
                          {weekUnavailable ? 'Weekly activity unavailable.'
                            : loading ? 'Updating weekly activity…'
                            : kidWeek
                              ? `${kidWeek.hours ?? 0}h clocked · ${formatCurrency(kidWeek.earnings)} clocked earnings`
                              : 'No clocked time this week.'}
                        </span>
                      </ParchmentCard>
                    </button>
                  );
                })}
              </div>
            ) : (
              <p className="font-body text-caption text-ink-secondary">Open Manage family to see your children.</p>
            )}

            <div className="flex flex-wrap gap-2 mt-4">
              {/* Labels match the Homework and Chores tabs. */}
              <Button variant="secondary" size="sm" onClick={() => navigate('/quests?tab=study&new=1')}>
                Assign homework
              </Button>
              <Button variant="secondary" size="sm" onClick={() => navigate('/quests?tab=duties&propose=1')}>
                New chore
              </Button>
              <Button variant="secondary" size="sm" onClick={() => navigate('/manage')}>
                Manage family
              </Button>
            </div>
          </section>

          <OnboardingChecklist data={dashboard} />

          <AccordionSection
            title="Quick adjusts"
            kicker="manual ledger corrections"
            icon={<Settings2 size={18} />}
            tone="ink"
            peek="Adjust coins · Adjust payment"
          >
            <QuickAdjustRow />
          </AccordionSection>
        </>
      )}
    </PageShell>
  );
}
