import { useEffect, useId, useRef, useState } from 'react';
import { ArrowLeft, ChevronRight, Compass } from 'lucide-react';
import Button from '../../components/Button';
import CatalogSearch from '../../components/CatalogSearch';
import EmptyState from '../../components/EmptyState';
import ParchmentCard from '../../components/journal/ParchmentCard';
import SkillVerse from '../achievements/SkillVerse';
import WayfinderSkillDetail from '../achievements/WayfinderSkillDetail';
import { WayfinderCategoryMap, WayfinderHeading, WayfinderSubjectMap } from '../achievements/WayfinderMap';
import { SKILL_CATEGORIES, SKILL_CATALOG, SKILL_PROGRESS } from './showcase.fixtures';

const OVERVIEW = { categoryId: null, subjectId: null, skillId: null };
const categoryPath = (categoryId) => ({ categoryId, subjectId: null, skillId: null });

/** A local, read-only journey through the production Wayfinder presentation. */
export default function SkillsShowcase() {
  const titleId = useId();
  const [path, setPath] = useState(OVERVIEW);
  const [history, setHistory] = useState([]);
  const [filter, setFilter] = useState('');
  const surfaceRef = useRef(null);
  const focusPending = useRef(false);
  const category = SKILL_CATEGORIES.find((entry) => entry.id === path.categoryId);
  const subjects = SKILL_CATALOG.subjects.filter((entry) => entry.category === path.categoryId).map((entry) => ({
    ...entry,
    skills: SKILL_CATALOG.skills.filter((candidate) => candidate.subject === entry.id).map((candidate) => ({
      ...candidate, ...SKILL_PROGRESS[candidate.id],
    })),
  }));
  const subject = subjects.find((entry) => entry.id === path.subjectId);
  const skill = subject?.skills.find((entry) => entry.id === path.skillId);
  const query = filter.trim().toLowerCase();
  const matches = (subject ? [subject] : subjects).map((owner) => ({
    ...owner,
    skills: owner.skills.filter((entry) => !query || `${entry.name} ${entry.description}`.toLowerCase().includes(query)),
  })).filter((owner) => owner.skills.length > 0);

  useEffect(() => {
    if (!focusPending.current) return;
    const heading = surfaceRef.current?.querySelector('h2');
    if (heading) {
      heading.tabIndex = -1;
      heading.focus({ preventScroll: true });
      surfaceRef.current.scrollIntoView?.({ block: 'start', behavior: 'auto' });
    }
    focusPending.current = false;
  }, [path]);

  function navigate(next) {
    setHistory((entries) => [...entries, path].slice(-50));
    setPath(next);
    setFilter('');
    focusPending.current = true;
  }

  function goBack() {
    setPath(history.at(-1) || OVERVIEW);
    setHistory((entries) => entries.slice(0, -1));
    setFilter('');
    focusPending.current = true;
  }

  function prerequisiteDestination(prerequisite) {
    const target = SKILL_CATALOG.skills.find((entry) => entry.id === prerequisite.skill_id);
    const owner = SKILL_CATEGORIES.find((entry) => entry.id === target?.category);
    return owner ? { categoryId: owner.id, categoryName: owner.name, subjectId: target.subject, skillId: target.id } : null;
  }

  const crumbs = [{ label: 'All skills', target: OVERVIEW }];
  if (category) crumbs.push({ label: category.name, target: categoryPath(category.id) });
  if (subject) crumbs.push({ label: subject.name, target: { ...path, skillId: null } });
  if (skill) crumbs.push({ label: skill.name, target: path });
  const currentName = skill?.name || subject?.name || category?.name || 'Your skills';

  return (
    <section id="skills" aria-labelledby={titleId} className="space-y-4">
      <header className="space-y-2">
        <h2 id={titleId} className="font-display text-2xl font-bold text-ink-primary">Skills · Wayfinder</h2>
        <p className="font-body text-body text-ink-secondary max-w-prose">
          Synthetic catalog and progress examples. Explore Category → Subject → Skill,
          search a branch, or follow Inlay Work’s requirement into Art & Crafts.
          These examples stay on this page and never update an account.
        </p>
      </header>
      <ParchmentCard ref={surfaceRef} tone="bright" className="skill-wayfinder scroll-mt-24 space-y-4">
        <div className="flex items-center gap-2 text-caption font-medium text-sheikah-teal-deep">
          <Compass size={17} aria-hidden="true" /> Wayfinder
        </div>
        <nav aria-label="Skills demo breadcrumb" className="wayfinder-breadcrumb">
          <ol className="flex flex-wrap items-center gap-1 min-w-0">
            {crumbs.map((entry, index) => (
              <li key={index} className="flex items-center gap-1 min-w-0">
                {index > 0 && <ChevronRight size={13} aria-hidden="true" className="shrink-0 text-ink-whisper" />}
                {index === crumbs.length - 1
                  ? <span aria-current="page" className="py-2 px-1 text-caption text-ink-primary break-words">{entry.label}</span>
                  : <Button variant="ghost" size="sm" className="!px-1 text-caption" onClick={() => navigate(entry.target)}>{entry.label}</Button>}
              </li>
            ))}
          </ol>
        </nav>
        {!category ? <>
          <WayfinderHeading title="Your skills" icon={<Compass aria-hidden="true" />} meta={`${SKILL_CATEGORIES.length} categories`} />
          <WayfinderCategoryMap categories={SKILL_CATEGORIES} catalog={SKILL_CATALOG} onSelectCategory={(id) => navigate(categoryPath(id))} />
        </> : <>
          {!skill && <WayfinderHeading title={subject?.name || category.name} icon={subject?.icon || category.icon}
            description={subject?.description || category.description}
            meta={subject ? `${subject.skills.length} skills · ${category.name}` : `${subjects.length} subjects`} />}
          {!skill && <CatalogSearch value={filter} onChange={setFilter} ariaLabel="Filter demo skills"
            placeholder={`Search skills in ${subject?.name || category.name}…`} />}
          {!skill && !subject && !query && <WayfinderSubjectMap category={category} subjects={subjects}
            onSelectSubject={(entry) => navigate({ ...path, subjectId: entry.id, skillId: null })} />}
          {!skill && (subject || query) && (matches.length
            ? matches.map((owner) => <section key={owner.id} aria-label={`${owner.name} skills`} className="space-y-3">
              {!subject && <h3 className="font-display font-semibold text-lede text-ink-primary">{owner.name}</h3>}
              <div className="wayfinder-skill-path">
                {owner.skills.map((entry, index) => <SkillVerse key={entry.id} variant="wayfinder" skill={entry} index={index}
                  onSelect={() => navigate({ ...path, subjectId: owner.id, skillId: entry.id })} />)}
              </div>
            </section>)
            : <EmptyState>No skills match your search. Try another word, or clear the filter.</EmptyState>)}
          {skill && <WayfinderSkillDetail skill={skill} resolvePrerequisite={prerequisiteDestination}
            onSelectPrerequisite={(prerequisite) => {
              const destination = prerequisiteDestination(prerequisite);
              if (destination) navigate(destination);
            }} />}
          <div className="wayfinder-footer">
            <Button variant="ghost" size="sm" onClick={goBack}><ArrowLeft size={16} aria-hidden="true" className="inline mr-2" />Back</Button>
            <span className="text-caption text-ink-whisper">Category → Subject → Skill</span>
          </div>
        </>}
        <p role="status" aria-live="polite" className="sr-only">{currentName}, {skill ? 'skill detail' : subject ? 'subject' : category ? 'category' : 'category atlas'}</p>
      </ParchmentCard>
    </section>
  );
}
