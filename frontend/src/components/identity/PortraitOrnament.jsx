import { useId } from 'react';

function Star({ x, y, size = 5 }) {
  return <path d={`M${x} ${y - size}l${size * 0.3} ${size * 0.7}L${x + size} ${y}l-${size * 0.7} ${size * 0.3}L${x} ${y + size}l-${size * 0.3}-${size * 0.7}L${x - size} ${y}l${size * 0.7}-${size * 0.3}Z`} fill="currentColor" stroke="none" />;
}
function Laurel() {
  return <>
    <path d="M45 91C13 83 4 47 23 16M55 91C87 83 96 47 77 16" />
    {[0, 1, 2, 3, 4].map((index) => <g key={index} transform={`rotate(${index * 18 - 10} 50 50)`}>
      <ellipse cx="13" cy="50" rx="4.5" ry="9" transform="rotate(-28 13 50)" fill="currentColor" stroke="none" />
      <ellipse cx="87" cy="50" rx="4.5" ry="9" transform="rotate(28 87 50)" fill="currentColor" stroke="none" />
    </g>)}
    <path d="M42 90l8-5 8 5-8 5Z" fill="var(--color-gold-leaf)" stroke="none" />
  </>;
}

function Gear({ x, y, radius = 12 }) {
  const points = Array.from({ length: 48 }, (_, index) => {
    const angle = (index * Math.PI) / 24;
    const distance = index % 4 < 2 ? radius : radius * 0.77;
    return `${x + Math.cos(angle) * distance},${y + Math.sin(angle) * distance}`;
  }).join(' ');
  return <g><polygon points={points} fill="var(--color-ink-page)" strokeWidth="2.5" /><circle cx={x} cy={y} r={radius * 0.38} strokeWidth="2.5" /></g>;
}

function FrameDrawing({ family }) {
  switch (family) {
    case 'bronze': return <><circle cx="50" cy="50" r="42" strokeWidth="5" /><circle cx="50" cy="50" r="36" strokeWidth="1.5" />{[0, 90, 180, 270].map((angle) => <circle key={angle} cx="50" cy="8" r="2.5" fill="var(--color-ink-page)" transform={`rotate(${angle} 50 50)`} />)}</>;
    case 'silver': return <><path d="M29 8h42l21 21v42L71 92H29L8 71V29Z" strokeWidth="5" /><path d="M32 14h36l18 18v36L68 86H32L14 68V32Z" strokeWidth="1.5" /><path d="M29 8l7 10M71 8l-7 10M8 71l12-5M92 29l-12 5" /></>;
    case 'gold': return <><circle cx="50" cy="53" r="39" strokeWidth="5" /><circle cx="50" cy="53" r="33" strokeWidth="1.5" /><path d="m33 13 3-9 9 7 5-9 5 9 9-7 3 9-5 7H38Z" fill="currentColor" stroke="none" /><Star x={50} y={90} size={6} /></>;
    case 'cosmic': return <><circle cx="50" cy="50" r="38" strokeWidth="5" /><ellipse cx="50" cy="50" rx="47" ry="19" transform="rotate(-35 50 50)" strokeWidth="3" /><Star x={25} y={14} size={7} /><Star x={86} y={39} size={5} /><circle cx="22" cy="86" r="3" fill="currentColor" /></>;
    case 'barbute': return <><path d="M14 86V44C14 18 29 7 50 7s36 11 36 37v42L71 73V42H29v31Z" fill="var(--color-ink-page-aged)" strokeWidth="5" /><path d="M50 8v20M28 31h44M14 78l12-8M86 78l-12-8" /><circle cx="21" cy="46" r="3" fill="currentColor" /><circle cx="79" cy="46" r="3" fill="currentColor" /></>;
    case 'robin-hood': return <><circle cx="50" cy="53" r="38" strokeWidth="4" /><path d="M10 32Q40 3 75 16l12 18q-42-13-77-2Z" fill="var(--color-ink-page-aged)" /><path d="M69 29C90 24 94 10 87 4 75 8 72 18 69 29Z" fill="currentColor" /><path d="m69 32 18-25" stroke="var(--color-ink-page)" strokeWidth="2" /></>;
    case 'cross-helm': return <><path d="M13 16 50 6l37 10v37Q86 79 50 95 14 79 13 53Z" strokeWidth="5" /><path d="M22 22 50 14l28 8v31Q76 75 50 85 24 75 22 53Z" strokeWidth="1.5" /><path d="M50 7v17M41 16h18M19 56l7 8M81 56l-7 8" strokeWidth="4" /></>;
    case 'scholar': return <><circle cx="50" cy="49" r="38" strokeWidth="3.5" /><path d="m17 15 33-11 33 11-33 12Z" fill="var(--color-ink-page-aged)" /><path d="M27 20v9q23 8 46 0v-9M83 15v22" /><path d="M18 80q17-8 32 2 15-10 32-2v13q-17-6-32 1-15-7-32-1Z" fill="var(--color-ink-page)" /><path d="M50 83v11M24 85l17 2M59 87l17-2" strokeWidth="1.5" /></>;
    case 'laurel': return <><circle cx="50" cy="50" r="33" strokeWidth="2" /><Laurel /></>;
    case 'rune-circle': return <><circle cx="50" cy="50" r="44" strokeWidth="2.5" /><circle cx="50" cy="50" r="35" strokeWidth="3" />{[0, 60, 120, 180, 240, 300].map((angle) => <path key={angle} d="m46 12 4-5 4 5-4 5Z" transform={`rotate(${angle} 50 50)`} fill="var(--color-ink-page)" strokeWidth="2" />)}</>;
    case 'steampunk': return <><circle cx="50" cy="50" r="39" strokeWidth="6" /><circle cx="50" cy="50" r="33" strokeDasharray="4 6" strokeWidth="2" /><Gear x={20} y={19} /><Gear x={82} y={70} radius={14} /><Gear x={24} y={87} radius={9} /></>;
    case 'pixel': return <><path d="M23 7h54v8h8v8h8v54h-8v8h-8v8H23v-8h-8v-8H7V23h8v-8h8Z" strokeWidth="5" strokeLinejoin="miter" /><path d="M29 17h42v7h7v7h7M15 67v9h9v9h9" strokeWidth="4" /><path d="M26 13h7M80 46v8M47 87h8" stroke="var(--color-ink-page)" strokeWidth="4" /></>;
    case 'high-school-trophy': return <><circle cx="50" cy="47" r="37" strokeWidth="4" /><path d="M35 73h30v7q0 10-15 10T35 80Zm0 2H25q0 12 14 12M65 75h10q0 12-14 12M50 90v6M40 96h20" fill="var(--color-ink-page)" /><Star x={50} y={13} size={8} /></>;
    case 'moonlit': return <><circle cx="50" cy="50" r="39" strokeWidth="4" /><path d="M81 4q-15 14 4 27C62 34 61 6 81 4Z" fill="currentColor" stroke="none" /><Star x={22} y={17} size={6} /><Star x={12} y={69} size={4} /><path d="M26 86q25 14 48-1" strokeWidth="6" /></>;
    case 'confetti': return <><circle cx="50" cy="50" r="38" strokeWidth="4" />{[0, 45, 90, 135, 180, 225, 270, 315].map((angle, index) => <g key={angle} transform={`rotate(${angle} 50 50)`} stroke={index % 2 ? 'var(--color-moss)' : 'currentColor'}><path d="m45 6 6 5" strokeWidth="5" /><circle cx="62" cy="12" r="2" fill="var(--color-gold-leaf)" stroke="none" /></g>)}</>;
    case 'seashell': return <><path d="M50 7q9-9 16 2 12-3 15 10 13 3 10 15 10 7 2 17 7 11-3 18 1 12-12 14-3 12-15 8-11 9-19-1-12 5-17-7-13-1-12-14Q4 61 11 51 3 40 13 33q-3-12 10-15 3-12 15-9 5-6 12-2Z" strokeWidth="3" /><path d="M34 91q-9-18 2-17 3-10 9-5 5-8 10 0 8-5 10 5 11-1 1 17Z" fill="var(--color-ink-page)" /><path d="m50 91-5-21M50 91l5-21M50 91 36 76M50 91l14-15" strokeWidth="1.5" /></>;
    case 'chronicle': return <><path d="M17 7h64q9 0 9 9v69q-35-8-73 5-7-6-7-15V19q0-12 7-12Z" fill="var(--color-ink-page-aged)" strokeWidth="4" /><circle cx="53" cy="46" r="30" strokeWidth="2" /><path d="M19 8v76M10 84q42-11 80 0M76 8v14l-7-4-7 4V8" /><path d="M35 90h35" strokeWidth="2" /></>;
    case 'far-horizons': return <><circle cx="50" cy="49" r="40" strokeWidth="4" /><path d="m13 80 15-15 18 15 18-17 23 17" fill="var(--color-ink-page)" /><path d="M24 88h53M16 75h15M69 75h16" strokeWidth="2" /><path d="M38 14a12 12 0 0 1 24 0M34 14h32M50 2v4M31 5l4 4M69 5l-4 4" strokeWidth="2.5" /></>;
    default: return <circle cx="50" cy="50" r="42" strokeWidth="5" />;
  }
}

export default function PortraitOrnament({ family }) {
  const openingId = useId();
  return <svg data-portrait-ornament="true" aria-hidden="true" viewBox="0 0 100 100" focusable="false" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round">
    <defs>
      {/* Black and white encode mask coverage, independent of cover colors.
          The opening matches the portrait's 17% inset, keeping every ornament
          outside the face even when its silhouette has a filled background. */}
      <mask id={openingId} maskUnits="userSpaceOnUse" x="0" y="0" width="100" height="100">
        <rect width="100" height="100" fill="white" stroke="none" />
        {family === 'pixel'
          ? <rect data-portrait-opening="true" x="17" y="17" width="66" height="66" rx="7.92" fill="black" stroke="none" />
          : <circle data-portrait-opening="true" cx="50" cy="50" r="33" fill="black" stroke="none" />}
      </mask>
    </defs>
    <g mask={`url(#${openingId})`}><FrameDrawing family={family} /></g>
  </svg>;
}
