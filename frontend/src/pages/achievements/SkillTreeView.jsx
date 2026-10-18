import { useEffect, useRef, useState } from 'react';
import { ArrowLeft, ChevronRight, Compass } from 'lucide-react';
import { getSkillCatalog, getSkillTree } from '../../api';
import { friendlyErrorMessage, useApi } from '../../hooks/useApi';
import Button from '../../components/Button';
import CatalogSearch from '../../components/CatalogSearch';
import EmptyState from '../../components/EmptyState';
import ErrorAlert from '../../components/ErrorAlert';
import Loader from '../../components/Loader';
import ParchmentCard from '../../components/journal/ParchmentCard';
import SkillVerse from './SkillVerse';
import WayfinderSkillDetail from './WayfinderSkillDetail';
import { WayfinderCategoryMap, WayfinderHeading, WayfinderSubjectMap } from './WayfinderMap';

const OVERVIEW = { view: 'overview', categoryId: null, subjectId: null, skillId: null };
const sameId = (left, right) => left == null || right == null
  ? left === right
  : String(left) === String(right);

function categoryPath(categoryId) {
  return { view: 'category', categoryId, subjectId: null, skillId: null };
}

function resolveSelection(path, category, tree) {
  if (!category) return { path: OVERVIEW, category: null, subject: null, skill: null };
  const base = { category: { ...category, ...tree?.category }, subject: null, skill: null };
  if (!tree || path.view === 'category') return { ...base, path };
  // A parent may move a skill after the global catalog metadata was loaded.
  // Its current subject and progress always come from the selected server tree.
  if (path.view === 'skill') {
    for (const subject of tree.subjects) {
      const skill = (subject.skills || []).find((entry) => sameId(entry.id, path.skillId));
      if (skill) return { ...base, subject, skill, path: { ...path, subjectId: subject.id } };
    }
  }
  const subject = tree.subjects.find((entry) => sameId(entry.id, path.subjectId));
  if (subject) return { ...base, subject, path: { ...path, view: 'subject', skillId: null } };
  return { ...base, path: categoryPath(category.id) };
}

/** Category atlas → subject branches → skills → inline skill detail. */
export default function SkillTreeView({ categories = [] }) {
  const [navigation, setNavigation] = useState(OVERVIEW);
  const [history, setHistory] = useState([]);
  const [filter, setFilter] = useState('');
  const [loaded, setLoaded] = useState(null);
  const [retry, setRetry] = useState(0);
  const surfaceRef = useRef(null);
  const focusPending = useRef(false);
  const { data: catalog, loading: catalogLoading, error: catalogError, reload: reloadCatalog } = useApi(getSkillCatalog);
  const category = categories.find((entry) => sameId(entry.id, navigation.categoryId));
  const categoryId = category?.id ?? null;
  const loadKey = categoryId == null ? null : `${categoryId}:${retry}`;
  const currentLoad = loadKey != null && loaded?.key === loadKey ? loaded : null;
  const tree = currentLoad?.tree ?? null;
  const treeLoading = categoryId != null && !currentLoad;
  const treeError = currentLoad?.error;
  const { path, category: activeCategory, subject, skill } = resolveSelection(navigation, category, tree);

  useEffect(() => {
    if (categoryId == null) return;
    let current = true;
    getSkillTree(categoryId)
      .then((response) => {
        if (!response || !Array.isArray(response.subjects)
          || (response.category?.id != null && !sameId(response.category.id, categoryId))) {
          throw new Error('This skill branch could not be read.');
        }
        if (current) setLoaded({ key: loadKey, tree: response, error: null });
      })
      .catch((error) => {
        if (current) setLoaded({ key: loadKey, tree: null, error: friendlyErrorMessage(error) });
      });
    return () => { current = false; };
  }, [categoryId, loadKey]);

  // Navigation restores focus after explicit input; metadata loads and mount
  // never steal focus. Keep the destination clear of the sticky journal header.
  useEffect(() => {
    if (!focusPending.current || treeLoading) return;
    const heading = surfaceRef.current?.querySelector('h2');
    if (heading) {
      heading.tabIndex = -1;
      heading.focus({ preventScroll: true });
      surfaceRef.current.scrollIntoView?.({ block: 'start', behavior: 'auto' });
    }
    focusPending.current = false;
  }, [path.view, path.categoryId, path.subjectId, path.skillId, treeLoading]);

  function navigate(next) {
    setHistory((previous) => [...previous, path].slice(-50));
    setNavigation(next);
    setFilter('');
    focusPending.current = true;
  }

  function goBack() {
    setNavigation(history.at(-1) || (path.view === 'skill'
      ? { ...path, view: 'subject', skillId: null }
      : path.view === 'subject' ? categoryPath(categoryId) : OVERVIEW));
    setHistory((entries) => entries.slice(0, -1));
    setFilter('');
    focusPending.current = true;
  }

  function selectSubject(nextSubject) {
    navigate({ view: 'subject', categoryId, subjectId: nextSubject.id, skillId: null });
  }

  function selectSkill(nextSkill, owner = subject) {
    navigate({ view: 'skill', categoryId, subjectId: owner.id, skillId: nextSkill.id });
  }

  function prerequisiteDestination(prerequisite) {
    for (const owner of tree?.subjects || []) {
      const target = (owner.skills || []).find((entry) => sameId(entry.id, prerequisite.skill_id));
      if (target) return {
        view: 'skill', categoryId, categoryName: activeCategory.name,
        subjectId: owner.id, skillId: target.id,
      };
    }
    const target = catalog?.skills.find((entry) => sameId(entry.id, prerequisite.skill_id));
    const owner = target && categories.find((entry) => sameId(entry.id, target.category));
    return owner ? {
      view: 'skill', categoryId: owner.id, categoryName: owner.name,
      subjectId: target.subject ?? null, skillId: target.id,
    } : null;
  }

  const query = filter.trim().toLowerCase();
  const searchableSubjects = path.view === 'subject' ? (subject ? [subject] : []) : (tree?.subjects || []);
  const matches = searchableSubjects.map((entry) => ({
    ...entry,
    skills: (entry.skills || []).filter((candidate) => !query
      || (candidate.name || '').toLowerCase().includes(query)
      || (candidate.description || '').toLowerCase().includes(query)),
  })).filter((entry) => entry.skills.length > 0);
  const hasSkills = searchableSubjects.some((entry) => entry.skills?.length);
  const metadataSubject = subject || catalog?.subjects.find((entry) => sameId(entry.id, path.subjectId));
  const metadataSkill = skill || catalog?.skills.find((entry) => sameId(entry.id, path.skillId));
  const breadcrumb = [{ label: 'All skills', target: OVERVIEW }];
  if (activeCategory) breadcrumb.push({ label: activeCategory.name, target: categoryPath(categoryId) });
  if (['subject', 'skill'].includes(path.view)) breadcrumb.push({
    label: metadataSubject?.name || 'Other', target: { ...path, view: 'subject', skillId: null },
  });
  if (path.view === 'skill') breadcrumb.push({ label: metadataSkill?.name || 'Skill', target: path });

  if (!categories.length) return <EmptyState>
    <div className="text-body font-medium text-ink-primary mb-1">No skill categories yet</div>
    <div className="text-caption">A parent can add them from Manage.</div>
  </EmptyState>;

  const currentName = skill?.name || subject?.name || activeCategory?.name || 'Your skills';
  return (
    <ParchmentCard tone="bright" ref={surfaceRef} className="skill-wayfinder scroll-mt-24 space-y-4">
      <div className="flex items-center gap-2 text-caption font-medium text-sheikah-teal-deep"><Compass size={17} aria-hidden="true" /> Skill explorer</div>
      <nav aria-label="Skill navigation" className="wayfinder-breadcrumb">
        <ol className="flex items-center flex-wrap gap-1 min-w-0">
          {breadcrumb.map((entry, index) => <li key={index} className="flex items-center gap-1 min-w-0">
            {index > 0 && <ChevronRight size={13} aria-hidden="true" className="shrink-0 text-ink-whisper" />}
            {index === breadcrumb.length - 1
              ? <span aria-current="page" className="py-2 px-1 text-caption text-ink-primary break-words">{entry.label}</span>
              : <Button variant="ghost" size="sm" className="!px-1 text-caption" onClick={() => navigate(entry.target)}>{entry.label}</Button>}
          </li>)}
        </ol>
      </nav>

      {catalogError && <div className="space-y-2">
        <ErrorAlert message={`Could not load the skill catalog. ${catalogError}`} />
        <Button variant="secondary" size="sm" onClick={reloadCatalog}>Retry skill catalog</Button>
      </div>}

      {path.view === 'overview' ? <>
        <WayfinderHeading title="Your skills" icon={<Compass aria-hidden="true" />} meta={`${categories.length} categories`} />
        {catalogLoading && <Loader />}
        <WayfinderCategoryMap categories={categories} catalog={catalog} onSelectCategory={(id) => navigate(categoryPath(id))} />
      </> : <>
        {!skill && <WayfinderHeading
          title={path.view === 'skill' ? (metadataSkill?.name || 'Skill') : subject?.name || activeCategory.name}
          icon={path.view === 'skill' ? metadataSkill?.icon : subject?.icon || activeCategory.icon}
          assetId={path.view === 'skill' ? metadataSkill?.catalog_icon : subject ? subject.catalog_icon : activeCategory.catalog_icon}
          description={subject?.description || (path.view === 'category' ? activeCategory.description : '')}
          meta={subject ? `${subject.skills?.length || 0} skills · ${activeCategory.name}`
            : tree?.summary ? `Level ${tree.summary.level} · ${(tree.summary.total_xp || 0).toLocaleString()} total XP` : ''}
        />}
        {treeLoading && <Loader />}
        {treeError && <div className="space-y-3">
          <ErrorAlert message={`Could not load this skill branch. ${treeError}`} />
          <Button variant="primary" onClick={() => { focusPending.current = true; setRetry((value) => value + 1); }}>Try again</Button>
        </div>}
        {tree && ['category', 'subject'].includes(path.view) && hasSkills && <CatalogSearch
          value={filter} onChange={setFilter} ariaLabel="Filter skills"
          placeholder={`Search skills in ${subject?.name || activeCategory.name}…`}
        />}
        {tree && path.view === 'category' && !query && <WayfinderSubjectMap category={activeCategory} subjects={tree.subjects} onSelectSubject={selectSubject} />}
        {tree && (path.view === 'subject' || (path.view === 'category' && query)) && (matches.length
          ? matches.map((owner) => <section key={owner.id ?? 'other'} aria-label={`${owner.name} skills`} className="space-y-3">
            {path.view === 'category' && <h3 className="font-display font-semibold text-lede text-ink-primary">{owner.name}</h3>}
            <div className="wayfinder-skill-path">
              {owner.skills.map((entry, index) => <SkillVerse key={entry.id} variant="wayfinder" skill={entry} index={index} onSelect={(selected) => selectSkill(selected, owner)} />)}
            </div>
          </section>) : <EmptyState>
            <div className="font-medium text-body text-ink-primary">{query ? 'No skills match your search' : 'No skills in this subject yet'}</div>
            {query && <div className="text-caption">Try another word, or clear the filter.</div>}
          </EmptyState>)}
        {tree && skill && <WayfinderSkillDetail skill={skill} resolvePrerequisite={prerequisiteDestination} catalogLoading={catalogLoading}
          onSelectPrerequisite={(prerequisite) => { const destination = prerequisiteDestination(prerequisite); if (destination) navigate(destination); }} />}
        <div className="wayfinder-footer">
          <Button variant="ghost" size="sm" onClick={goBack}><ArrowLeft size={16} aria-hidden="true" className="inline mr-2" />Back</Button>
          <span className="text-caption text-ink-whisper">Category → Subject → Skill</span>
        </div>
      </>}
      <p role="status" aria-live="polite" className="sr-only">{treeLoading ? 'Loading skills' : `${currentName}, ${path.view === 'overview' ? 'skill categories' : path.view}`}</p>
    </ParchmentCard>
  );
}
