/**
 * JournalIcons — custom line-art SVG icon set for the Hyrule Field Notes
 * aesthetic. Each icon uses `currentColor` for stroke so tailwind text-*
 * classes color them. Sized via `size` prop (default 20).
 *
 * Five primary icons match the five journal chapters:
 *   TodayIcon     — open book with a teardrop/flame
 *   QuestsIcon    — crossed quill + sword
 *   BestiaryIcon  — dragon head silhouette
 *   TreasuryIcon  — treasure chest with keyhole
 *   AtlasIcon     — folded map with rune marker
 *
 * Plus a few action/feature icons used across the app.
 */

const baseProps = (size) => ({
  width: size,
  height: size,
  viewBox: '0 0 24 24',
  fill: 'none',
  stroke: 'currentColor',
  strokeWidth: 1.5,
  strokeLinecap: 'round',
  strokeLinejoin: 'round',
  'aria-hidden': true,
});

export function TodayIcon({ size = 20, className = '' }) {
  return (
    <svg {...baseProps(size)} className={className}>
      <path d="M3 5 C 5 4, 11 4, 12 6 C 13 4, 19 4, 21 5 L 21 19 C 19 18, 13 18, 12 20 C 11 18, 5 18, 3 19 Z" />
      <path d="M12 6 L 12 20" />
      <path d="M12 10 C 11 11.5, 11 13, 12 14 C 13 13, 13 11.5, 12 10 Z" fill="currentColor" fillOpacity="0.35" />
    </svg>
  );
}

export function QuestsIcon({ size = 20, className = '' }) {
  return (
    <svg {...baseProps(size)} className={className}>
      {/* Sword */}
      <path d="M17 3 L 20 6 L 10 16 L 7 17 L 8 14 Z" />
      <path d="M6 18 L 8 20" />
      {/* Quill */}
      <path d="M4 20 C 7 16, 12 11, 16 8 C 14 12, 10 16, 6 20 Z" />
      <path d="M5 21 L 3 23" />
    </svg>
  );
}

export function BestiaryIcon({ size = 20, className = '' }) {
  return (
    <svg {...baseProps(size)} className={className}>
      <path d="M12 3 C 7 5, 5 10, 6 14 C 7 18, 10 20, 12 21 C 14 20, 17 18, 18 14 C 19 10, 17 5, 12 3 Z" />
      <circle cx="10" cy="11" r="0.8" fill="currentColor" />
      <circle cx="14" cy="11" r="0.8" fill="currentColor" />
      <path d="M10 14 C 11 15, 13 15, 14 14" />
      <path d="M6 14 C 3 15, 2 18, 3 20" />
      <path d="M18 14 C 21 15, 22 18, 21 20" />
    </svg>
  );
}

export function TreasuryIcon({ size = 20, className = '' }) {
  return (
    <svg {...baseProps(size)} className={className}>
      <path d="M3 9 C 5 7, 19 7, 21 9 L 21 19 L 3 19 Z" />
      <path d="M3 9 L 3 19 M21 9 L 21 19 M3 13 L 21 13" />
      <circle cx="12" cy="15.5" r="1.2" fill="currentColor" />
      <path d="M12 14.3 L 12 11" />
      <path d="M7 7 C 7 5, 17 5, 17 7" />
    </svg>
  );
}

export function AtlasIcon({ size = 20, className = '' }) {
  return (
    <svg {...baseProps(size)} className={className}>
      <path d="M3 6 L 9 4 L 15 6 L 21 4 L 21 18 L 15 20 L 9 18 L 3 20 Z" />
      <path d="M9 4 L 9 18 M15 6 L 15 20" />
      <circle cx="6.5" cy="13" r="1.2" fill="currentColor" />
      <path d="M6.5 11.8 L 6.5 9" />
    </svg>
  );
}

export function ClockFabIcon({ size = 22, className = '' }) {
  return (
    <svg {...baseProps(size)} className={className}>
      <circle cx="12" cy="12" r="9" />
      <circle cx="12" cy="12" r="6" strokeDasharray="2 3" strokeWidth="0.75" />
      <path d="M12 7 L 12 12 L 15.5 14" strokeWidth="2" />
      <circle cx="12" cy="12" r="1" fill="currentColor" />
    </svg>
  );
}

export function InkwellIcon({ size = 20, className = '' }) {
  return (
    <svg {...baseProps(size)} className={className}>
      <path d="M7 10 L 7 18 C 7 20, 17 20, 17 18 L 17 10 Z" />
      <path d="M7 10 C 7 8, 17 8, 17 10" />
      <path d="M12 8 L 12 3 L 19 3" />
      <path d="M10 14 L 14 14" />
    </svg>
  );
}

export function ScrollIcon({ size = 20, className = '' }) {
  return (
    <svg {...baseProps(size)} className={className}>
      <path d="M5 5 C 5 3, 19 3, 19 5 L 19 17 C 19 19, 5 19, 5 17 Z" />
      <path d="M5 5 C 5 7, 3 7, 3 5 C 3 3, 5 3, 5 5" />
      <path d="M19 17 C 19 19, 21 19, 21 17 C 21 15, 19 15, 19 17" />
      <path d="M8 9 L 16 9 M8 12 L 16 12 M8 15 L 13 15" />
    </svg>
  );
}

export function EggIcon({ size = 20, className = '' }) {
  return (
    <svg {...baseProps(size)} className={className}>
      <path d="M12 3 C 7 4, 5 11, 6 16 C 7 20, 17 20, 18 16 C 19 11, 17 4, 12 3 Z" />
      <path d="M8 11 C 9 12, 10 11, 11 12 M13 13 C 14 14, 15 13, 16 14" strokeDasharray="1.5 1.5" />
    </svg>
  );
}

export function CoinIcon({ size = 20, className = '' }) {
  return (
    <svg {...baseProps(size)} className={className}>
      <circle cx="12" cy="12" r="8" />
      <circle cx="12" cy="12" r="5" strokeDasharray="1.5 2" />
      <path d="M10 10 L 14 14 M14 10 L 10 14" />
    </svg>
  );
}

export function DragonIcon({ size = 20, className = '' }) {
  return (
    <svg {...baseProps(size)} className={className}>
      <path d="M4 14 C 6 12, 9 10, 12 10 C 16 10, 19 13, 20 16 L 17 16 L 16 19 L 12 18 L 10 21 L 9 17 L 5 17 Z" />
      <circle cx="17.5" cy="13.5" r="0.8" fill="currentColor" />
      <path d="M4 14 C 2 13, 2 10, 4 9" />
    </svg>
  );
}
