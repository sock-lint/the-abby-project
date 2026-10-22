import { useId } from 'react';
import './HeaderStreakFlame.css';

// The server supplies normalized bonus intensity. Saved streak days are
// deliberately absent: an old streak can still be asleep today.
export default function HeaderStreakFlame({ active = false, intensity = 0 }) {
  const gradientId = `header-flame-${useId()}`;
  const state = !active || !(intensity > 0) ? 'dormant'
    : intensity >= 1 ? 'blazing' : intensity >= 0.5 ? 'strong' : 'kindled';
  const outline = {
    kindled: 'M16 28C10 28 8 24 9 20C10 16 14 14 14 8C19 11 19 15 18 17C20 16 21 14 21 13C27 20 24 28 16 28Z',
    strong: 'M16 28C8 28 5 22 8 16C8 19 10 20 11 19C9 12 17 9 16 3C23 9 23 13 21 17C24 16 25 13 25 12C31 22 25 28 16 28Z',
    blazing: 'M16 28C6 28 2 21 6 13C6 17 9 17 9 16C8 9 15 8 16 2C21 6 23 10 21 14C25 13 26 9 25 7C33 15 30 28 16 28Z',
  }[state];

  return (
    <svg
      data-header-streak-flame=""
      data-state={state}
      viewBox="0 0 32 32"
      width="24"
      height="24"
      className="header-streak-flame shrink-0"
      aria-hidden="true"
      focusable="false"
    >
      <ellipse cx="16" cy="29" rx="9" ry="1.5" fill="currentColor" opacity="0.12" />
      {state === 'dormant' ? (
        <>
          <path d="M12 20C10 16 17 15 15 10" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" opacity="0.75" />
          <path d="M9 26Q9 22 16 22Q23 22 23 26Q16 30 9 26Z" fill="currentColor" opacity="0.75" />
          <path d="M13 25Q16 23 19 25" fill="none" stroke="var(--color-ink-page)" strokeWidth="1.5" strokeLinecap="round" />
        </>
      ) : (
        <>
          <defs>
            <linearGradient id={gradientId} x1="0" y1="1" x2="0.5" y2="0">
              <stop offset="0" stopColor="var(--color-ember-deep)" />
              <stop offset="0.55" stopColor="var(--color-ember)" />
              <stop offset="1" stopColor="var(--color-gold-leaf)" />
            </linearGradient>
          </defs>
          <g className="header-streak-flame__fire">
            <path d={outline} fill={`url(#${gradientId})`} stroke="var(--color-ember-deep)" strokeWidth="0.8" strokeLinejoin="round" />
            <path d="M16 27C12 27 11 24 12 22C13 20 16 19 16 16C22 21 22 27 16 27Z" fill="var(--color-gold-leaf)" />
            <path d="M16 27C13 27 14 24 16 22C18 24 19 27 16 27Z" fill="var(--color-ink-page)" />
            {(state === 'strong' || state === 'blazing') && <circle cx="6" cy="8" r="1.3" fill="var(--color-gold-leaf)" />}
            {state === 'blazing' && (
              <>
                <path d="M28 3L29 5L28 7L27 5Z" fill="var(--color-gold-leaf)" />
                <circle cx="4" cy="21" r="1" fill="var(--color-ember)" />
              </>
            )}
          </g>
        </>
      )}
    </svg>
  );
}
