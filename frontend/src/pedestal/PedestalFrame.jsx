import PedestalImage from './PedestalImage';
import './card-ui.css';

/** The supplied practical opening, with deliberate app padding. This frame is
 * a proportional overlay; it has no authored nine-slice or blank card slots. */
export default function PedestalFrame({ children, className = '', label = 'Framed content', staged }) {
  return <div className={`mt-frame ${className}`} data-pedestal-frame="true">
    <div className="mt-frame__content bg-ink-page text-ink-primary" data-pedestal-frame-content="true" role="region" aria-label={label} tabIndex={0}>{children}</div>
    <PedestalImage assetId="frame-gold" staged={staged} className="mt-frame__art" />
  </div>;
}
