import { Link } from 'react-router-dom';
import { motion } from 'framer-motion';
import { UserPlus } from 'lucide-react';
import HeroPrimaryCard from '../components/dashboard/HeroPrimaryCard';
import ApprovalQueueList from '../components/dashboard/ApprovalQueueList';
import AccordionSection from '../components/dashboard/AccordionSection';
import WeekGlanceBlock from '../components/dashboard/WeekGlanceBlock';
import QuickAdjustRow from '../components/dashboard/QuickAdjustRow';
import ParchmentCard from '../components/journal/ParchmentCard';
import Button from '../components/Button';
import useParentDashboard from '../hooks/useParentDashboard';
import { inkBleed } from '../motion/variants';
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
        <p className="font-script text-ink-secondary max-w-md mx-auto text-sm">
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
  const { pending, weekByKid, dashboard, reload } = useParentDashboard();
  const { weekday, dateStr } = formatWeekdayDate();

  // children_count is exposed by the parent dashboard payload. While the
  // dashboard request is in flight, treat it as "we don't know yet" and
  // fall back to whether any pending rows exist — that's enough to dodge
  // a flash of the empty-state on parents who already have kids.
  const childrenCount = dashboard?.children_count;
  const showWelcome = childrenCount === 0 && pending.length === 0;

  return (
    <motion.div variants={inkBleed} initial="initial" animate="animate" className="max-w-6xl mx-auto space-y-5">
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

          <ApprovalQueueList items={pending} onDone={reload} />

          <AccordionSection
            title="Week at a glance"
            kicker="per-kid hours and earnings"
            peek={weekByKid.length > 0 ? `${weekByKid.length} kid${weekByKid.length !== 1 ? 's' : ''} active` : 'no week data yet'}
          >
            <WeekGlanceBlock weekByKid={weekByKid} />
          </AccordionSection>

          <AccordionSection
            title="Quick adjusts"
            kicker="manual ledger corrections"
            peek="Adjust coins · Adjust payment"
          >
            <QuickAdjustRow />
          </AccordionSection>
        </>
      )}
    </motion.div>
  );
}
