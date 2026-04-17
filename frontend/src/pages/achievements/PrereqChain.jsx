import { Link2, Link2Off } from 'lucide-react';

/**
 * PrereqChain — a row of rune-chain links representing a skill's
 * prerequisites. Each link carries a data attribute for tests + screen
 * readers get a composed aria-label. A link that's met renders filled in
 * moss; unmet links are hollow with low opacity so the chain reads as
 * "still to forge". Desktop users get a `title` tooltip; mobile users get
 * the label via the accessible name when they focus it.
 */
export default function PrereqChain({ prerequisites }) {
  if (!prerequisites?.length) return null;

  return (
    <ul className="flex items-center gap-1 flex-wrap" aria-label="Prerequisites">
      {prerequisites.map((p) => {
        const label = `${p.skill_name} · Level ${p.required_level} · ${p.met ? 'met' : 'not yet met'}`;
        const Icon = p.met ? Link2 : Link2Off;
        return (
          <li key={p.skill_id ?? `${p.skill_name}-${p.required_level}`}>
            <span
              data-prereq-link="true"
              data-met={p.met ? 'true' : 'false'}
              role="img"
              aria-label={label}
              title={label}
              className={`inline-flex items-center justify-center w-5 h-5 ${
                p.met ? 'text-moss' : 'text-ink-whisper/50'
              }`}
            >
              <Icon size={14} strokeWidth={p.met ? 2.5 : 1.75} />
            </span>
          </li>
        );
      })}
    </ul>
  );
}
