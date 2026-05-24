import PageShell from '../components/layout/PageShell';
import ParchmentSkeleton from '../components/ParchmentSkeleton';

/**
 * DashboardSkeleton — a content-aware loading placeholder that matches the
 * ChildDashboard layout (hero + list + rail + cards). Shown while the
 * /api/dashboard/ payload is in flight so the page skeleton is recognizable
 * from the first paint, eliminating the layout shift that the generic
 * compass-rose Loader caused.
 */
export default function DashboardSkeleton() {
  return (
    <PageShell animate={false}>
      {/* Page header placeholder */}
      <div className="space-y-1">
        <div className="h-4 w-40 rounded bg-ink-page-shadow/30" />
        <div className="h-8 w-56 rounded bg-ink-page-shadow/30" />
      </div>

      {/* HeroPrimaryCard */}
      <ParchmentSkeleton variant="hero" />

      {/* VitalPipStrip placeholder — row of small pill shapes */}
      <div className="flex gap-3">
        {[1, 2, 3, 4].map((i) => (
          <div
            key={i}
            className="h-8 flex-1 rounded-full bg-ink-page-shadow/20"
          />
        ))}
      </div>

      {/* Quest log (list variant) */}
      <ParchmentSkeleton variant="list" count={4} />

      {/* Loot rail */}
      <ParchmentSkeleton variant="rail" count={4} />

      {/* Two accordion-style cards (Treasury, Next Up) */}
      <ParchmentSkeleton variant="card" />
      <ParchmentSkeleton variant="card" />
    </PageShell>
  );
}
