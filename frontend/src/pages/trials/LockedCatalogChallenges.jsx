import { useState } from 'react';
import { LockKeyhole } from 'lucide-react';
import AchievementCard from '../../components/cards/AchievementCard';
import BottomSheet from '../../components/BottomSheet';
import Button from '../../components/Button';
import ChapterRubric from '../../components/atlas/ChapterRubric';

function Requirements({ definition }) {
  const requirements = definition.milestone_eligibility?.requirements;
  if (!Array.isArray(requirements) || !requirements.length) return <p className="text-caption text-ink-secondary">Requirement details are unavailable. Refresh challenges to check again.</p>;
  return <ul aria-label={`${definition.name} milestone requirements`} className="space-y-2 text-body text-ink-secondary">
    {requirements.map((requirement, index) => <li key={`${requirement.kind}:${index}`} className="flex flex-wrap gap-x-2 gap-y-1">
      <span>{requirement.description || 'Requirement details unavailable'}</span>
      <span className={requirement.met === true ? 'font-semibold text-moss-deep' : 'font-semibold text-ink-secondary'}>{requirement.met === true ? 'Met' : requirement.met === false ? 'Not yet met' : 'Status unavailable'}</span>
    </li>)}
  </ul>;
}

function Availability({ definition }) {
  const unlocked = definition.milestone_eligibility?.unlocked;
  const descriptions = new Set((definition.milestone_eligibility?.requirements ?? []).map((requirement) => requirement.description));
  const extraReasons = (definition.milestone_eligibility?.locked_reasons ?? []).filter((reason) => !descriptions.has(reason));
  return <div className="space-y-2">
    <p className="font-semibold text-caption text-ink-secondary">{unlocked === true ? 'Requirements met' : unlocked === false ? 'Locked challenge' : 'Availability unavailable'}</p>
    {unlocked === true && <p className="text-body text-ink-secondary">Your next matching saved activity can start this challenge.</p>}
    <Requirements definition={definition} />
    {unlocked === false && extraReasons.length > 0 && <details>
      <summary className="min-h-11 py-3 cursor-pointer font-semibold text-caption text-ink-secondary">Why this challenge is locked</summary>
      <ul className="list-disc pl-5 space-y-1 text-caption text-ink-secondary">{extraReasons.map((reason, index) => <li key={index}>{reason}</li>)}</ul>
    </details>}
  </div>;
}

export default function LockedCatalogChallenges({ definitions = [], sectionIndex = 0 }) {
  const [selectedId, setSelectedId] = useState(null);
  const selected = definitions.find((definition) => definition.id === selectedId);
  if (!definitions.length) return null;
  return <section aria-label="Coming next" className="space-y-3">
    <ChapterRubric index={sectionIndex} name="Coming next" />
    <p className="font-body text-caption text-ink-secondary">These challenges become available after their milestones. Your saved challenges keep their current progress and deadlines.</p>
    <div className="grid grid-cols-1 xl:grid-cols-2 gap-3">{definitions.map((definition) => <AchievementCard key={definition.id} as="article" variant="tall" aria-label={`${definition.name} upcoming catalog challenge`}>
      <div className="space-y-3">
        <div className="flex items-start gap-2"><LockKeyhole size={18} aria-hidden="true" className="shrink-0 text-ink-secondary" /><h4 className="font-body font-bold text-lede text-ink-primary break-words [overflow-wrap:anywhere]">{definition.name}</h4></div>
        <Availability definition={definition} />
        <Button variant="secondary" size="sm" onClick={() => setSelectedId(definition.id)}>View requirements for {definition.name}</Button>
      </div>
    </AchievementCard>)}</div>
    {selected && <BottomSheet title={`${selected.name} requirements`} onClose={() => setSelectedId(null)}>
      <div className="space-y-4">
        {selected.description && <p className="font-body text-body text-ink-secondary">{selected.description}</p>}
        <Availability definition={selected} />
        <p className="font-body text-body text-ink-secondary">No deadline is running yet.{Number.isInteger(selected.duration_days) && selected.duration_days > 0 ? ` The completion window lasts ${selected.duration_days} days after it starts.` : ''}</p>
        <p className="font-body text-caption text-ink-secondary">This preview does not start, pin or complete the challenge.</p>
      </div>
    </BottomSheet>}
  </section>;
}
