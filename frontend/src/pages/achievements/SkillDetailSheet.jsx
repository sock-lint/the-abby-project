import BottomSheet from '../../components/BottomSheet';
import QuillProgress from '../../components/QuillProgress';
import IlluminatedVersal from '../../components/atlas/IlluminatedVersal';
import PrereqChain from './PrereqChain';
import { tierForProgress } from '../../components/atlas/mastery.constants';
import { XP_THRESHOLDS } from './skillTree.constants';

/**
 * SkillDetailSheet — illuminated detail pane for a single skill. Dropped
 * into the app via <BottomSheet> so mobile gets a slide-up and desktop
 * gets a centered stamp-in. Layout reads top-to-bottom like a manuscript
 * leaf: hero glyph in an ornate frame → level-name strap → quill progress
 * → level roadmap (filled/outlined dots) → rune-chain prereqs.
 */
export default function SkillDetailSheet({ skill, onClose }) {
  const current = XP_THRESHOLDS[skill.level] ?? 0;
  const next = XP_THRESHOLDS[skill.level + 1] ?? XP_THRESHOLDS[6];
  const span = Math.max(1, next - current);
  const inLevel = Math.max(0, skill.xp_points - current);
  const pct = skill.unlocked ? Math.min(100, (inLevel / span) * 100) : 0;
  const tier = tierForProgress({ unlocked: !!skill.unlocked, progressPct: pct, level: skill.level });
  const levelName = skill.level_names?.[String(skill.level)] || '';
  const maxed = skill.level >= 6;

  const levelEntries = Object.entries(skill.level_names || {})
    .map(([lvl, name]) => ({ lvl: Number(lvl), name }))
    .sort((a, b) => a.lvl - b.lvl);

  const firstLetter = (skill.name || '✦').trim().charAt(0).toUpperCase() || '✦';

  return (
    <BottomSheet title={skill.name} onClose={onClose}>
      <div className="space-y-4">
        {/* Illuminated hero: the skill's drop-capital, filling with gilt as
            XP accrues, wearing a rarity-tier halo once cresting or gilded. */}
        <div className="flex flex-col items-center text-center">
          <IlluminatedVersal
            letter={firstLetter}
            progressPct={pct}
            tier={tier}
            size="xl"
          />
          {skill.icon && (
            <div
              aria-hidden="true"
              className="mt-2 text-3xl leading-none opacity-80"
            >
              {skill.icon}
            </div>
          )}
          {skill.description && (
            <p className="mt-3 font-body text-body text-ink-whisper max-w-prose">
              {skill.description}
            </p>
          )}
        </div>

        {/* Level-name strap */}
        <div className="flex items-center justify-center gap-6">
          <div className="text-center">
            <div className={`font-display text-3xl font-bold leading-none ${tier.chip}`}>
              L{skill.level}
            </div>
            <div className="text-micro font-rune uppercase tracking-wider text-ink-whisper mt-1">
              current rank
            </div>
          </div>
          {levelName && (
            <div className="text-center">
              <div className="font-script text-lede text-sheikah-teal-deep leading-none">
                {levelName}
              </div>
              <div className="text-micro font-rune uppercase tracking-wider text-ink-whisper mt-1">
                title
              </div>
            </div>
          )}
          <div className="text-center">
            <div className="font-display text-3xl font-bold leading-none text-ink-primary">
              {skill.xp_points.toLocaleString()}
            </div>
            <div className="text-micro font-rune uppercase tracking-wider text-ink-whisper mt-1">
              total xp
            </div>
          </div>
        </div>

        {skill.unlocked && !maxed && (
          <div>
            <div className="flex items-center justify-between text-caption text-ink-whisper mb-1.5">
              <span className="font-script">ink toward L{skill.level + 1}</span>
              <span className="font-rune text-micro uppercase tracking-wider">
                {inLevel.toLocaleString()} / {span.toLocaleString()}
              </span>
            </div>
            <QuillProgress
              value={pct}
              color={tier.bar}
              aria-label={`${skill.name} XP progress toward level ${skill.level + 1}`}
            />
          </div>
        )}
        {skill.unlocked && maxed && (
          <div className="text-center font-script text-gold-leaf text-lede">
            ★ mastery sealed · no higher rank awaits
          </div>
        )}

        {/* Level roadmap */}
        {levelEntries.length > 0 && (
          <nav
            aria-label="Level roadmap"
            className="rounded-xl border border-ink-page-shadow bg-ink-page-aged/60 p-3"
          >
            <div className="text-caption font-rune uppercase tracking-wider text-ink-whisper mb-2">
              level roadmap
            </div>
            <ol className="space-y-1">
              {levelEntries.map(({ lvl, name }) => {
                const reached = lvl <= skill.level;
                return (
                  <li
                    key={lvl}
                    data-reached={reached ? 'true' : 'false'}
                    className={`flex items-center gap-3 text-body ${
                      reached ? 'text-ink-primary' : 'text-ink-whisper/70'
                    }`}
                  >
                    <span
                      aria-hidden="true"
                      className={`w-2.5 h-2.5 rounded-full shrink-0 ${
                        reached
                          ? 'bg-sheikah-teal-deep shadow-[0_0_8px_rgba(29,138,128,0.6)]'
                          : 'border border-ink-whisper/50'
                      }`}
                    />
                    <span className="font-display text-caption font-bold w-8 shrink-0 text-ember-deep">
                      L{lvl}
                    </span>
                    <span className={reached ? 'font-medium' : ''}>{name}</span>
                  </li>
                );
              })}
            </ol>
          </nav>
        )}

        {/* Prereq chain */}
        {skill.prerequisites?.length > 0 && (
          <div className="rounded-xl border border-ink-page-shadow bg-ink-page-aged/60 p-3">
            <div className="text-caption font-rune uppercase tracking-wider text-ink-whisper mb-2">
              rune bindings
            </div>
            <ul className="space-y-1.5">
              {skill.prerequisites.map((p) => (
                <li key={p.skill_id} className="flex items-center gap-2 text-body">
                  <PrereqChain prerequisites={[p]} />
                  <span className={p.met ? 'text-moss' : 'text-ink-whisper'}>
                    {p.skill_name} · Level {p.required_level}
                  </span>
                </li>
              ))}
            </ul>
          </div>
        )}

        {!skill.unlocked && (
          <div className="text-center text-caption italic text-ink-whisper">
            this skill is locked — forge its bindings first
          </div>
        )}
      </div>
    </BottomSheet>
  );
}
