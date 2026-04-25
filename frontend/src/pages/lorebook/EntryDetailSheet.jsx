import BottomSheet from '../../components/BottomSheet';
import Button from '../../components/Button';
import { ECONOMY_FLAGS, economyFlagLabel } from './lorebook.constants';

function Paragraphs({ text }) {
  return String(text || '')
    .split(/\n\s*\n/)
    .map((paragraph) => paragraph.trim())
    .filter(Boolean)
    .map((paragraph) => (
      <p key={paragraph.slice(0, 40)} className="text-sm leading-relaxed text-ink-secondary">
        {paragraph}
      </p>
    ));
}

function EconomyPills({ economy = {} }) {
  return (
    <div className="flex flex-wrap gap-1.5">
      {ECONOMY_FLAGS.map((flag) => {
        const yes = !!economy[flag.key];
        return (
          <span
            key={flag.key}
            className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-micro font-rune uppercase tracking-wider ${
              yes
                ? 'border-moss/30 bg-moss/10 text-moss'
                : 'border-ink-whisper/20 bg-ink-page-aged/40 text-ink-whisper'
            }`}
          >
            <span aria-hidden="true">{yes ? '✓' : '—'}</span>
            {economyFlagLabel(flag.key)}
          </span>
        );
      })}
    </div>
  );
}

export { EconomyPills };

function ParentKnobs({ entry }) {
  const knobs = entry.parent_knobs || {};
  const settings = knobs.settings || [];
  const badges = knobs.powers_badges || [];
  const sources = knobs.content_sources || [];

  if (!settings.length && !badges.length && !sources.length) {
    return (
      <p className="text-sm text-ink-whisper italic">
        No special parent knobs for this page yet.
      </p>
    );
  }

  return (
    <div className="space-y-4">
      {settings.length > 0 && (
        <div>
          <h4 className="font-display text-sm font-semibold text-ink-primary mb-2">
            Tunable settings
          </h4>
          <ul className="space-y-2">
            {settings.map((setting) => (
              <li
                key={setting.key}
                className="rounded-lg border border-ink-page-shadow bg-ink-page/45 px-3 py-2"
              >
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-rune text-tiny uppercase tracking-wider text-sheikah-teal-deep">
                    {setting.key}
                  </span>
                  <span className="text-caption text-ink-primary">{setting.label}</span>
                </div>
                <div className="mt-1 text-caption text-ink-whisper">
                  Current default: <span className="text-ink-secondary">{String(setting.value)}</span>
                </div>
              </li>
            ))}
          </ul>
        </div>
      )}

      {badges.length > 0 && (
        <div>
          <h4 className="font-display text-sm font-semibold text-ink-primary mb-2">
            Badge criteria this powers
          </h4>
          <div className="flex flex-wrap gap-1.5">
            {badges.map((badge) => (
              <span
                key={badge}
                className="rounded-full bg-gold-leaf/10 border border-gold-leaf/25 px-2 py-0.5 text-micro font-rune uppercase tracking-wider text-gold-leaf"
              >
                {badge}
              </span>
            ))}
          </div>
        </div>
      )}

      {sources.length > 0 && (
        <div>
          <h4 className="font-display text-sm font-semibold text-ink-primary mb-2">
            Authoring notes
          </h4>
          <ul className="list-disc pl-5 space-y-1 text-sm text-ink-secondary">
            {sources.map((source) => (
              <li key={source}>{source}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

export default function EntryDetailSheet({
  entry,
  onClose,
  mode = 'kid',
  parentPanelsDefaultOpen = false,
}) {
  if (!entry) return null;
  const parentMode = mode === 'parent';

  return (
    <BottomSheet title={entry.title} onClose={onClose}>
      <div className="space-y-5">
        <header className="text-center">
          <div className="text-5xl mb-2" aria-hidden="true">{entry.icon || '📖'}</div>
          <div className="font-script text-sheikah-teal-deep text-base">
            {entry.audience_title || 'a field note'}
          </div>
          <p className="mt-1 text-sm text-ink-whisper">{entry.summary}</p>
        </header>

        <section className="space-y-3">
          <h3 className="font-display italic text-xl text-ink-primary">
            In the journal voice
          </h3>
          <div className="space-y-2">
            <Paragraphs text={entry.kid_voice} />
          </div>
        </section>

        <section className="space-y-3 rounded-xl border border-ink-page-shadow bg-ink-page-aged/45 p-3">
          <h3 className="font-display italic text-xl text-ink-primary">
            How it actually works
          </h3>
          <ul className="space-y-2">
            {(entry.mechanics || []).map((item) => (
              <li key={item} className="flex gap-2 text-sm text-ink-secondary leading-relaxed">
                <span className="mt-1 h-1.5 w-1.5 rounded-full bg-sheikah-teal-deep shrink-0" />
                <span>{item}</span>
              </li>
            ))}
          </ul>
          <EconomyPills economy={entry.economy} />
        </section>

        <details
          open={parentPanelsDefaultOpen || parentMode}
          className="rounded-xl border border-ink-page-shadow bg-ink-page/45 p-3"
        >
          <summary className="cursor-pointer font-display text-base font-semibold text-ink-primary">
            For parents: knobs, gates, and catalog notes
          </summary>
          <div className="mt-3">
            <ParentKnobs entry={entry} />
          </div>
        </details>

        <Button variant="secondary" onClick={onClose} className="w-full">
          Close
        </Button>
      </div>
    </BottomSheet>
  );
}
