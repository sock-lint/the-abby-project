import { useContext } from 'react';
import SectionHeader from '../../components/SectionHeader';
import AchievementCard from '../../components/cards/AchievementCard';
import AchievementCardIcon from '../../components/cards/AchievementCardIcon';
import { DesignPreviewContext } from './preview.context';

export default function AchievementCardShowcase() {
  const { longContent } = useContext(DesignPreviewContext);
  return <section id="design-achievement-cards" aria-label="Achievement card kit" className="space-y-3 scroll-mt-4">
    <SectionHeader title="Achievement card kit" kicker="Private release preview" />
    <p className="text-body text-ink-secondary">Paired backgrounds and borders surround live app content. The illustrations below are contextual examples and do not assign artwork or rewards to any badge.</p>
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 items-start">
      <AchievementCard variant="wide" contentClassName="space-y-2">
        <h3 className="font-bold text-lede">Compact Profile card</h3>
        <p className="text-body text-ink-secondary">{longContent ? 'A thoughtful achievement with a long, descriptive name that can wrap and grow without covering its border or hiding the action.' : 'Existing badge identity and rarity stay in live content.'}</p>
      </AchievementCard>
      <AchievementCard variant="tall" contentClassName="space-y-2">
        <h3 className="font-bold text-lede">Collection, challenge and reward card</h3>
        <p className="text-body text-ink-secondary">{longContent ? 'Long descriptions, measured progress and available actions determine the height of this card. Its original corners keep their shape at every size.' : 'Text and controls set the height; the 64px corner slices stay proportional.'}</p>
      </AchievementCard>
    </div>
    {['book', 'heart', 'compass'].map((icon) => <div key={icon} className="space-y-2">
      <h3 className="text-body font-bold capitalize">{icon}</h3>
      <div className="flex flex-wrap items-end gap-4">
        {[24, 32, 40, 64, 96].map((size) => <figure key={size} className="flex flex-col items-center gap-1">
          <AchievementCardIcon icon={icon} size={size} label={`${icon} illustration at ${size} pixels`} />
          <figcaption className="text-caption text-ink-secondary">{size}px</figcaption>
        </figure>)}
      </div>
    </div>)}
    <p className="text-caption text-ink-secondary">Profile uses the wide pair; badge collections, challenges and rewards use the tall pair. Missing or failed artwork retains a readable surface and live controls.</p>
  </section>;
}
