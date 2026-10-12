import { ArrowUpRight, Check, Lock, Route } from 'lucide-react';
import Button from '../../components/Button';
import QuillProgress from '../../components/QuillProgress';
import { tierForProgress } from '../../components/atlas/mastery.constants';
import { WayfinderHeading } from './WayfinderMap';
import { XP_THRESHOLDS } from './skillTree.constants';

/** Inline detail keeps prerequisite journeys inside the same atlas history. */
export default function WayfinderSkillDetail({ skill, resolvePrerequisite = () => null, onSelectPrerequisite, catalogLoading = false }) {
  const level = skill.level ?? 0;
  const xp = skill.xp_points ?? 0;
  const current = XP_THRESHOLDS[level] ?? 0;
  const next = XP_THRESHOLDS[level + 1] ?? XP_THRESHOLDS[6];
  const maxed = level >= 6;
  const pct = Math.max(0, Math.min(100, ((xp - current) / Math.max(1, next - current)) * 100));
  const tier = tierForProgress({ unlocked: !!skill.unlocked, progressPct: pct, level });
  const levelName = skill.level_names?.[String(level)];
  const prerequisites = skill.prerequisites || [];
  return <div className="space-y-4">
    <WayfinderHeading title={skill.name} icon={skill.icon || skill.name?.[0]}
      description={skill.description} meta={`Level ${level}${levelName ? ` · ${levelName}` : ''} · ${xp.toLocaleString()} XP`} />
    {skill.unlocked ? (maxed ? <p className="font-medium text-body text-gold-leaf">Maximum level reached</p> : <div className="space-y-2">
      <div className="flex flex-wrap justify-between gap-2 text-caption text-ink-whisper">
        <span>{Math.max(0, next - xp).toLocaleString()} XP to Level {level + 1}</span><span>{Math.round(pct)}% toward next level</span>
      </div>
      <QuillProgress value={pct} color={tier.bar} aria-label={`${skill.name} XP progress toward level ${level + 1}`} />
    </div>) : <div className="flex items-start gap-2 rounded-lg bg-ink-page-aged p-3 text-body text-ink-secondary">
      <Lock size={17} aria-hidden="true" className="shrink-0 mt-0.5" />
      <p>{prerequisites.length ? 'Locked — meet these skill requirements to unlock.' : 'This skill is locked and has not unlocked yet.'}</p>
    </div>}
    {prerequisites.length > 0 && <section aria-label="Prerequisite paths" className="space-y-2">
      <h3 className="font-display font-semibold text-body text-ink-secondary">Prerequisite paths</h3>
      {prerequisites.map((prerequisite) => {
        const destination = resolvePrerequisite(prerequisite);
        const met = prerequisite.met;
        return <Button key={prerequisite.skill_id ?? prerequisite.skill_name} variant="ghost"
          className="flex w-full items-center gap-3 rounded-lg text-left !font-normal" disabled={!destination}
          onClick={() => onSelectPrerequisite?.(prerequisite)}>
          <span aria-hidden="true" className={`flex size-8 shrink-0 items-center justify-center rounded-full border border-ink-page-shadow ${met ? 'text-moss' : 'text-sheikah-teal-deep'}`}>
            {met ? <Check size={16} /> : <Route size={16} />}
          </span>
          <span className="min-w-0 flex-1">
            <span className="block font-medium text-body text-ink-primary break-words">{prerequisite.skill_name}</span>
            <span className="block text-caption text-ink-whisper mt-1">
              {destination?.categoryName && <>{destination.categoryName} · </>}
              Requires Level {prerequisite.required_level} · {met === true ? 'Met' : met === false ? 'Not yet met' : 'Requirement status unavailable'}
            </span>
            {!destination && <span className="block text-caption text-ink-whisper mt-1">{catalogLoading ? 'Loading destination…' : 'Destination unavailable'}</span>}
          </span>
          {destination && <ArrowUpRight size={16} aria-hidden="true" className="shrink-0" />}
        </Button>;
      })}
    </section>}
    <section className="space-y-3">
      <h3 className="font-display font-semibold text-body text-ink-secondary">Level names</h3>
      <ol aria-label="Level roadmap" className="grid grid-cols-2 md:grid-cols-3 gap-4">
        {Object.entries(XP_THRESHOLDS).filter(([value]) => Number(value) > 0).map(([value, threshold]) => {
          const reached = level >= Number(value);
          return <li key={value} data-reached={reached ? 'true' : 'false'} className="relative pt-3 border-t border-ink-page-shadow">
            <span aria-hidden="true" className={`absolute -top-1 left-0 size-2 rounded-full ${reached ? 'bg-gold-leaf' : 'bg-ink-page-shadow'}`} />
            <div className="text-caption text-ink-whisper">Level {value} · {threshold.toLocaleString()} XP</div>
            <div className="text-body text-ink-primary mt-1 break-words">{skill.level_names?.[value] || (Number(value) === 6 ? 'Mastery' : `Level ${value}`)}</div>
            {reached && <span className="sr-only">Reached</span>}
          </li>;
        })}
      </ol>
    </section>
  </div>;
}
