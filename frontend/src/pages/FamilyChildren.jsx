import { Link, Navigate } from 'react-router-dom';
import { getChildOverview } from '../api';
import { useApi } from '../hooks/useApi';
import useChildContext from '../hooks/useChildContext';
import { useSpace } from '../hooks/useSpace';
import ChildContext from '../components/family/ChildContext';
import PageShell from '../components/layout/PageShell';
import SectionHeader from '../components/SectionHeader';
import ParchmentCard from '../components/journal/ParchmentCard';
import Loader from '../components/Loader';
import ErrorAlert from '../components/ErrorAlert';
import EmptyState from '../components/EmptyState';
import { companionFormName, companionStage } from '../companion/lifecycle';

function OverviewList({ title, rows, total = rows.length, empty, children }) {
  return <section className="space-y-3" aria-label={title}>
    <SectionHeader title={title} count={total} />
    {rows.length ? <>
      <ul className="grid gap-3 sm:grid-cols-2">{rows.slice(0, 8).map(children)}</ul>
      {total > 8 && <p className="text-caption text-ink-secondary">Showing {Math.min(8, rows.length)} of {total}.</p>}
    </> : <p className="text-body text-ink-secondary">{empty}</p>}
  </section>;
}

function CreatureRow({ creature, kind = 'pet' }) {
  const form = companionFormName(creature.species, creature.potion, companionStage(creature, kind));
  return <li><ParchmentCard className="space-y-1">
    <p className="font-semibold text-body text-ink-primary break-words">{creature.name || form}</p>
    {creature.name && <p className="text-caption text-ink-secondary">{form}</p>}
    {creature.is_active && <p className="text-caption text-sheikah-teal-deep">{kind === 'mount' ? 'Active grown pet' : 'Active companion'}</p>}
  </ParchmentCard></li>;
}

function ChildOverview({ childId }) {
  const { data, loading, refreshing, error, reload } = useApi(
    (signal) => getChildOverview(childId, { signal }), [childId],
  );
  if (loading) return <Loader />;
  if (error || !data || String(data.child?.id) !== String(childId)) {
    return <ErrorAlert message={error || 'Could not verify this child’s overview. Please try again.'} onRetry={reload} />;
  }
  const skills = data.skills ?? [];
  const badges = data.badges ?? [];
  const pets = data.pets ?? [];
  const mounts = data.mounts ?? [];
  const name = data.child.display_name || data.child.display_label || data.child.username || 'Your child';
  return <div className="space-y-6">
    {refreshing && <p role="status" className="text-caption text-ink-secondary">Updating this child’s overview…</p>}
    <ParchmentCard className="space-y-4">
      <h2 className="font-display text-xl text-ink-primary break-words">{name}</h2>
      <dl className="grid grid-cols-2 gap-4">
        <div><dt className="text-caption text-ink-secondary">Level</dt><dd className="font-semibold text-xl text-ink-primary">{data.level ?? 'Unavailable'}</dd></div>
        <div><dt className="text-caption text-ink-secondary">Coins</dt><dd className="font-semibold text-xl text-ink-primary">{data.coin_balance ?? 'Unavailable'}</dd></div>
      </dl>
      <div className="flex flex-wrap gap-3">
        <Link to={`/quests?child=${childId}`} className="inline-flex min-h-11 items-center font-semibold text-body text-sheikah-teal-deep">View tasks</Link>
        <Link to={`/chronicle?tab=journal&child=${childId}`} className="inline-flex min-h-11 items-center font-semibold text-body text-sheikah-teal-deep">Shared memories</Link>
        <Link to={`/chronicle?tab=yearbook&child=${childId}`} className="inline-flex min-h-11 items-center font-semibold text-body text-sheikah-teal-deep">View timeline</Link>
      </div>
      <p className="text-caption text-ink-secondary">Journals and grades appear in Memories only when your child shares them with parents.</p>
    </ParchmentCard>
    <OverviewList title="Skills" rows={skills} total={data.counts?.skills} empty="No skill progress recorded yet.">{(skill) => <li key={skill.id}><ParchmentCard>
      <p className="font-semibold text-body text-ink-primary">{skill.skill_name}</p>
      <p className="text-caption text-ink-secondary">Level {skill.level} · {skill.xp_points} XP</p>
    </ParchmentCard></li>}</OverviewList>
    <OverviewList title="Earned badges" rows={badges} total={data.counts?.badges} empty="No badges earned yet.">{(earned) => <li key={earned.id}><ParchmentCard>
      <p className="font-semibold text-body text-ink-primary">{earned.badge?.name || 'Saved badge'}</p>
    </ParchmentCard></li>}</OverviewList>
    <OverviewList title="Companions" rows={pets} total={data.counts?.pets} empty="No companions collected yet.">{(pet) => <CreatureRow key={pet.id} creature={pet} />}</OverviewList>
    <OverviewList title="Grown pets" rows={mounts} total={data.counts?.mounts} empty="No grown pets yet.">{(mount) => <CreatureRow key={mount.id} creature={mount} kind="mount" />}</OverviewList>
  </div>;
}

export default function FamilyChildren() {
  const context = useChildContext();
  const { isParentAccount, isFamilySpace } = useSpace();
  if (!context.user) return <Loader />;
  if (!isParentAccount || !isFamilySpace) return <Navigate to="/" replace />;
  return <PageShell>
    <SectionHeader as="h1" title="Children">See each child’s progress, companions and shared memories.</SectionHeader>
    {context.loading ? <Loader /> : context.error ? <ErrorAlert message={context.error} onRetry={context.reload} /> : !context.children?.length ? <EmptyState action={<Link to="/manage" className="inline-flex min-h-11 items-center font-semibold text-sheikah-teal-deep">Manage family</Link>}>Add a child to see their progress here.</EmptyState> : <>
      <ChildContext children={context.children} selectedChildId={context.targetUserId} onSelect={context.selectChild} />
      <ChildOverview key={`${context.scope}:${context.targetUserId}`} childId={context.targetUserId} />
    </>}
  </PageShell>;
}
