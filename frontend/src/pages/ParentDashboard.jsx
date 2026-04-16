import { motion } from 'framer-motion';
import HeroPrimaryCard from '../components/dashboard/HeroPrimaryCard';
import ApprovalQueueList from '../components/dashboard/ApprovalQueueList';
import KidStrip from '../components/dashboard/KidStrip';
import AccordionSection from '../components/dashboard/AccordionSection';
import WeekGlanceBlock from '../components/dashboard/WeekGlanceBlock';
import QuickAdjustRow from '../components/dashboard/QuickAdjustRow';
import useParentDashboard from '../hooks/useParentDashboard';
import { inkBleed } from '../motion/variants';
import { formatWeekdayDate } from './_dashboardShared';

export default function ParentDashboard() {
  const { pending, kids, weekByKid, reload } = useParentDashboard();
  const { weekday, dateStr } = formatWeekdayDate();

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

      <HeroPrimaryCard
        role="parent"
        ctx={{
          weekday, dateStr,
          pendingCount: pending.length,
        }}
      />

      <ApprovalQueueList items={pending} onDone={reload} />

      <KidStrip kids={kids} />

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
    </motion.div>
  );
}
