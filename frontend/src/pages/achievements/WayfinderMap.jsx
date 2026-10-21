import Button from '../../components/Button';
import EmptyState from '../../components/EmptyState';
import ArtworkImage from '../../components/rpg/ArtworkImage';
import { taxonomyStatus } from '../../utils/taxonomy';
import './WayfinderMap.css';

function countLabel(count, name) {
  return `${count} ${name}${count === 1 ? '' : 's'}`;
}

function belongsToCategory(item, category) {
  return item.category != null && String(item.category) === String(category.id);
}

/** The icon can be a catalog emoji or a shared chapter/utility icon. */
export function WayfinderHeading({ title, icon, assetId, description, meta }) {
  return (
    <header className="wayfinder-heading">
      <span className="wayfinder-heading-icon" aria-hidden="true"><ArtworkImage assetId={assetId} fallback={icon || '✦'} size={40} /></span>
      <div className="wayfinder-heading-copy">
        <h2>{title}</h2>
        {description && <p>{description}</p>}
        {meta && <div className="wayfinder-meta">{meta}</div>}
      </div>
    </header>
  );
}

/** Category destinations contain catalog counts, never estimated progress. */
export function WayfinderCategoryMap({ categories = [], catalog, onSelectCategory }) {
  if (!categories.length) {
    return <EmptyState>No skill categories yet.</EmptyState>;
  }

  return (
    <>
      <div className="wayfinder-origin">Choose a category</div>
      <ul className="wayfinder-category-map" aria-label="Skill categories">
        {categories.map((category) => {
          const subjects = catalog?.subjects?.filter((subject) => belongsToCategory(subject, category));
          const skills = catalog?.skills?.filter((skill) => belongsToCategory(skill, category));
          const meta = catalog
            ? `${countLabel(subjects?.length ?? 0, 'subject')} · ${countLabel(skills?.length ?? 0, 'skill')}`
            : null;

          return (
            <li key={category.id}>
              <Button
                variant="ghost"
                className="wayfinder-category-node"
                aria-label={[category.name, meta, taxonomyStatus(category, 'category')].filter(Boolean).join(', ')}
                onClick={() => onSelectCategory(category.id)}
              >
                <span className="wayfinder-marker" aria-hidden="true"><ArtworkImage assetId={category.catalog_icon} fallback={category.icon || '✦'} size={32} /></span>
                <span className="wayfinder-node-copy">
                  <strong>{category.name}</strong>
                  {taxonomyStatus(category, 'category') && <small>{taxonomyStatus(category, 'category')}</small>}
                  {meta && <small>{meta}</small>}
                </span>
              </Button>
            </li>
          );
        })}
      </ul>
    </>
  );
}

/** Branches group real skills; they do not imply prerequisite order. */
export function WayfinderSubjectMap({ category, subjects = [], onSelectSubject }) {
  if (!subjects.length) {
    return <EmptyState>No subjects or skills in this category yet.</EmptyState>;
  }

  return (
    <>
      <div className="wayfinder-origin">{category?.name || 'Choose a subject'}</div>
      <ul
        className="wayfinder-subject-map"
        aria-label={`${category?.name || 'Category'} subjects`}
        style={{ '--wayfinder-branches': Math.min(subjects.length, 3) }}
      >
        {subjects.map((subject, index) => {
          const skills = subject.skills || [];
          const name = subject.name || 'Other';
          return (
            <li key={subject.id ?? `other-${index}`} className="wayfinder-subject-branch">
              <Button
                variant="ghost"
                className="wayfinder-destination"
                aria-label={[name, countLabel(skills.length, 'skill'), taxonomyStatus(subject, 'subject')].filter(Boolean).join(', ')}
                onClick={() => onSelectSubject(subject)}
              >
                <span className="wayfinder-marker" aria-hidden="true"><ArtworkImage assetId={subject.catalog_icon} fallback={subject.icon || category?.icon || '✦'} size={32} /></span>
                <span className="wayfinder-node-copy">
                  <strong>{name}</strong>
                  {taxonomyStatus(subject, 'subject') && <small>{taxonomyStatus(subject, 'subject')}</small>}
                  <small>{countLabel(skills.length, 'skill')}</small>
                </span>
              </Button>
              {skills.length ? (
                <ul className="wayfinder-subject-preview" aria-label={`${name} skill preview`}>
                  {skills.map((skill) => <li key={skill.id}>{skill.name}</li>)}
                </ul>
              ) : (
                <p className="wayfinder-subject-preview-empty">No skills yet</p>
              )}
            </li>
          );
        })}
      </ul>
    </>
  );
}
