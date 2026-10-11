import { getDashboard } from '../api';
import { useApi } from '../hooks/useApi';
import { useRole } from '../hooks/useRole';
import ErrorAlert from '../components/ErrorAlert';
import ChildDashboard from './ChildDashboard';
import ParentDashboard from './ParentDashboard';
import DashboardSkeleton from './DashboardSkeleton';
import { formatWeekdayDate } from './_dashboardShared';
import PageShell from '../components/layout/PageShell';
import PageHeader from '../components/layout/PageHeader';

/**
 * Dashboard — the "Today" page. Thin router that loads dashboard data once,
 * then defers to role-specific bodies. The top-level loader + error retry
 * live here so existing integration tests continue to cover both roles.
 */
export default function Dashboard() {
  const { data, loading, error, reload } = useApi(getDashboard);
  const { isParent } = useRole();

  if (loading) return <DashboardSkeleton />;
  if (error || !data) {
    return (
      <PageShell animate={false}>
        <DateHeader />
        <ErrorAlert message={error || 'Could not load today. Please try again.'} onRetry={reload} />
      </PageShell>
    );
  }

  return isParent ? <ParentDashboard /> : <ChildDashboard data={data} reload={reload} />;
}

function DateHeader() {
  const { weekday, dateStr } = formatWeekdayDate();
  return (
    <PageHeader title="Today" kicker={`${weekday} · ${dateStr}`} />
  );
}
