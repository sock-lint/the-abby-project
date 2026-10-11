import { ArrowRight } from 'lucide-react';
import { MEADOW_COMPANION, MEADOW_TOKENS } from './meadow.constants';
import './meadow.css';

export default function MeadowVisitCard() {
  return (
    <a href="/play/" aria-label="Visit Play, your companion and rewards" className="meadow-visit" style={MEADOW_TOKENS}>
      <img src={MEADOW_COMPANION.portrait} alt="" width="88" height="88" />
      <span className="meadow-visit-copy">
        <span className="meadow-eyebrow">Your companion and rewards</span>
        <span className="meadow-visit-title">Visit Play</span>
        <span>Spend a moment with your companion and see what you’ve earned.</span>
      </span>
      <ArrowRight size={22} aria-hidden="true" />
    </a>
  );
}
