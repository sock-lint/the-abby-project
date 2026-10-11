// Rounded storybook drawings with soft fills from the active Meadow cover.
// Existing exports and size/className props remain compatible with callers.
function MeadowIcon({ name, size = 20, children, ...props }) {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.7}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
      data-meadow-icon={name}
      {...props}
    >
      {children}
    </svg>
  );
}

export function TodayIcon(props) {
  return (
    <MeadowIcon name="home" {...props}>
      <path d="M5 10.5V19a1.5 1.5 0 0 0 1.5 1.5h11A1.5 1.5 0 0 0 19 19v-8.5L12 5Z" fill="var(--color-moss)" fillOpacity=".18" />
      <path d="m3 11 8-7a1.5 1.5 0 0 1 2 0l8 7M9.5 20.5v-5a2.5 2.5 0 0 1 5 0v5" />
      <path d="M15.5 6V3.5H18V8M7.5 11h1" />
    </MeadowIcon>
  );
}

export function QuestsIcon(props) {
  return (
    <MeadowIcon name="adventure" {...props}>
      <path d="M6 20V4.5c3-3 7 3 12 0v9c-5 3-9-3-12 0" fill="var(--color-royal)" fillOpacity=".16" />
      <path d="m11.5 6.5.8 1.7 1.7.8-1.7.8-.8 1.7-.8-1.7L9 9l1.7-.8Z" fill="var(--color-gold-leaf)" fillOpacity=".35" />
      <path d="M3 20.5h6M18.5 17.5l.5 1 .5-1 1-.5-1-.5-.5-1-.5 1-1 .5Z" />
    </MeadowIcon>
  );
}

export function BestiaryIcon(props) {
  return (
    <MeadowIcon name="companions" {...props}>
      <path d="M7 14.5c1.8-1.2 2.5-4 5-4s3.2 2.8 5 4c3 2 1.5 6-1.5 5.5-2-.4-2.5-1-3.5-1s-1.5.6-3.5 1C5.5 20.5 4 16.5 7 14.5Z" fill="var(--color-rose)" fillOpacity=".2" />
      <ellipse cx="5" cy="9" rx="1.8" ry="2.4" transform="rotate(-20 5 9)" fill="var(--color-rose)" fillOpacity=".2" />
      <ellipse cx="9.5" cy="5.5" rx="1.7" ry="2.3" transform="rotate(-8 9.5 5.5)" fill="var(--color-rose)" fillOpacity=".2" />
      <ellipse cx="14.5" cy="5.5" rx="1.7" ry="2.3" transform="rotate(8 14.5 5.5)" fill="var(--color-rose)" fillOpacity=".2" />
      <ellipse cx="19" cy="9" rx="1.8" ry="2.4" transform="rotate(20 19 9)" fill="var(--color-rose)" fillOpacity=".2" />
    </MeadowIcon>
  );
}

export function TreasuryIcon(props) {
  return (
    <MeadowIcon name="treasure" {...props}>
      <path d="M3 11V9a6 6 0 0 1 6-6h6a6 6 0 0 1 6 6v2Z" fill="var(--color-gold-leaf)" fillOpacity=".24" />
      <path d="M3 11v7a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7Z" fill="var(--color-moss)" fillOpacity=".16" />
      <path d="M7 4v7M17 4v7M7 15v5M17 15v5" />
      <rect x="10" y="9.5" width="4" height="5" rx="1.5" fill="var(--color-gold-leaf)" fillOpacity=".4" />
      <path d="M12 11.5v1" />
    </MeadowIcon>
  );
}

export function AtlasIcon(props) {
  return (
    <MeadowIcon name="atlas" {...props}>
      <path d="m3 5 6-2 6 2 6-2v16l-6 2-6-2-6 2Z" fill="var(--color-moss)" fillOpacity=".16" />
      <path d="M9 3v16M15 5v16M11 14c1-2 2.5-3 5-3" strokeDasharray="1 3" />
      <path d="M16 10c0-3 2-4 4-4 0 2-1 4-4 4Z" fill="var(--color-moss)" fillOpacity=".35" />
    </MeadowIcon>
  );
}

export function ChronicleIcon(props) {
  return (
    <MeadowIcon name="memories" {...props}>
      <path d="M12 6C9 3 5 3.5 2.5 4.5v15c3-1 6.5-1 9.5 1.5 3-2.5 6.5-2.5 9.5-1.5v-15C19 3.5 15 3 12 6Z" fill="var(--color-royal)" fillOpacity=".13" />
      <path d="M12 6v15M5.5 9H9M5.5 12H9M5.5 15H8" />
      <path d="M16.5 15v-4c-3 0-3-4 0-3 3-1 3 3 0 3m0 2c0-2 2-2 3-2 0 2-1 3-3 3" fill="var(--color-moss)" fillOpacity=".25" />
    </MeadowIcon>
  );
}

export function ClockFabIcon({ size = 22, ...props }) {
  return (
    <MeadowIcon name="clock" size={size} {...props}>
      <circle cx="12" cy="12" r="9" fill="var(--color-royal)" fillOpacity=".13" />
      <path d="M12 7v5l3 2M12 3v1M21 12h-1M12 21v-1M3 12h1" />
    </MeadowIcon>
  );
}

export function InkwellIcon(props) {
  return (
    <MeadowIcon name="pencil" {...props}>
      <path d="m5 15-1 5 5-1L20 8a2.8 2.8 0 0 0-4-4Z" fill="var(--color-gold-leaf)" fillOpacity=".2" />
      <path d="m14 6 4 4M5 15l4 4M4 20h5" />
    </MeadowIcon>
  );
}

export function ScrollIcon(props) {
  return (
    <MeadowIcon name="scroll" {...props}>
      <path d="M6 6a3 3 0 0 0-3-3h13a3 3 0 0 1 3 3v12a3 3 0 0 1-3 3H8a2 2 0 0 1-2-2Z" fill="var(--color-gold-leaf)" fillOpacity=".16" />
      <path d="M6 6H2V5a2 2 0 0 1 4 0M19 17h3v1a3 3 0 0 1-6 0v-1H6M9 8h6M9 11h4" />
    </MeadowIcon>
  );
}

export function EggIcon(props) {
  return (
    <MeadowIcon name="egg" {...props}>
      <path d="M20 14c0 4.5-3.6 7-8 7s-8-2.5-8-7C4 9 8.5 3 12 3s8 6 8 11Z" fill="var(--color-gold-leaf)" fillOpacity=".18" />
      <path d="m7.5 13 2 1M14.5 8l1 1M14.5 16l1.5-1" stroke="var(--color-moss)" strokeWidth="2.5" />
    </MeadowIcon>
  );
}

export function CoinIcon(props) {
  return (
    <MeadowIcon name="coin" {...props}>
      <circle cx="12" cy="12" r="9" fill="var(--color-gold-leaf)" fillOpacity=".3" />
      <circle cx="12" cy="12" r="6.5" strokeOpacity=".35" />
      <path d="M12 16v-4m0 1c-3 0-4-2-4-4 3 0 4 1 4 4Zm0-2c0-3 2-4 4-4 0 3-1 4-4 4Z" fill="var(--color-moss)" fillOpacity=".35" />
    </MeadowIcon>
  );
}

export function DragonIcon(props) { return <BestiaryIcon {...props} />; }
