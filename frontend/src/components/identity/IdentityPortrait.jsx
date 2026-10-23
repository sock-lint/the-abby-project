import { Sparkles } from 'lucide-react';
import ProfilePortrait from './ProfilePortrait';

/** A confirmed level belongs beneath the saved portrait, outside its artwork. */
export default function IdentityPortrait({ level, ...portraitProps }) {
  const hasLevel = Number.isInteger(level) && level >= 0;
  return <span className={`identity-portrait ${hasLevel ? 'identity-portrait--leveled' : ''}`}>
    <ProfilePortrait {...portraitProps} />
    {hasLevel && <span className="identity-portrait__level" role="img" aria-label={`Level ${level}`}>
      <Sparkles size={12} aria-hidden="true" />
      <span aria-hidden="true">Lv. {level}</span>
    </span>}
  </span>;
}
