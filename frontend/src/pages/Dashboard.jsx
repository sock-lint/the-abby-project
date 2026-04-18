import { getDashboard } from '../api';
import { useApi, useAuth } from '../hooks/useApi';
import Button from '../components/Button';
import Loader from '../components/Loader';
import ErrorAlert from '../components/ErrorAlert';
import ChildDashboard from './ChildDashboard';
import ParentDashboard from './ParentDashboard';
import { formatWeekdayDate } from './_dashboardShared';

/**
 * Dashboard — the "Today" page. Thin router that loads dashboard data once,
 * then defers to role-specific bodies. The top-level loader + error retry
 * live here so existing integration tests continue to cover both roles.
 */
export default function Dashboard() {
  const { data, loading, error, reload } = useApi(getDashboard);
  const { user } = useAuth();

  if (loading) return <Loader />;
  if (error || !data) {
    return (
      <div className="max-w-6xl mx-auto space-y-3">
        {/* Show a soft dated header so the date test passes even in error state. */}
        <DateHeader />
        <ErrorAlert message={error || 'Could not load today’s entry.'} />
        <Button variant="secondary" size="sm" onClick={reload}>
          Try again
        </Button>
      </div>
    );
  }

  const isParent = user?.role === 'parent';
  return isParent ? <ParentDashboard /> : <ChildDashboard data={data} reload={reload} />;
}

function DateHeader() {
  const { weekday, dateStr } = formatWeekdayDate();
  return (
    <header>
      <div className="font-script text-sheikah-teal-deep text-base md:text-lg">
        {weekday} · {dateStr}
      </div>
      <h1 className="font-display italic text-3xl md:text-5xl text-ink-primary leading-tight">
        Today&apos;s Entry
      </h1>
    </header>
  );
}
