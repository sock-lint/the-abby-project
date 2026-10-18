import { useState } from 'react';
import { createRoot } from 'react-dom/client';
import '../src/index.css';
import { applyTheme } from '../src/themes';
import ArtworkShowcase from '../src/pages/design/ArtworkShowcase';
import BadgeSigil from '../src/components/atlas/BadgeSigil';
import BadgeArtwork from '../src/components/atlas/BadgeArtwork';
import BadgeDetailSheet from '../src/pages/achievements/BadgeDetailSheet';
import BirthdayCelebrationModal from '../src/components/BirthdayCelebrationModal';
import { WayfinderCategoryMap, WayfinderSubjectMap } from '../src/pages/achievements/WayfinderMap';
import SkillVerse from '../src/pages/achievements/SkillVerse';
import Button from '../src/components/Button';
import CatalogIcon from '../src/components/rpg/CatalogIcon';
import badges from '../../contracts/api/fixtures/artwork-badges.json';
import categories from '../../contracts/api/fixtures/artwork-categories.json';
import tree from '../../contracts/api/fixtures/artwork-tree.json';

const theme = new URLSearchParams(window.location.search).get('theme');
applyTheme(theme === 'vigil' ? 'vigil' : 'hyrule');

export default function Fixture() {
  const [detail, setDetail] = useState(null);
  const [birthday, setBirthday] = useState(false);
  const badge = badges.results[0];
  return <main className="p-4 max-w-5xl mx-auto space-y-6 bg-ink-page text-ink-primary">
    <h1 className="text-2xl">Private artwork acceptance</h1>
    <section aria-label="Production components" className="space-y-4">
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <BadgeSigil badge={badge} earned onSelect={setDetail} />
        <BadgeSigil badge={badge} earned={false} onSelect={setDetail} />
        <div aria-label="Featured badge"><BadgeArtwork badge={badge} earned variant="featured" /></div>
        <BadgeSigil badge={badges.results[1]} earned />
      </div>
      <div className="skill-wayfinder">
        <WayfinderCategoryMap categories={categories.results} onSelectCategory={() => {}} />
        <WayfinderSubjectMap category={tree.category} subjects={tree.subjects} onSelectSubject={() => {}} />
        <SkillVerse skill={tree.subjects[0].skills[0]} variant="wayfinder" />
      </div>
      <div className="flex gap-4">
        <CatalogIcon assetId="item-accessory-crown" icon="CROWN" alt="Crown (saved only)" size={40} />
        <CatalogIcon assetId="item-summer-2026-food-watermelon" icon="MELON" alt="Watermelon Slice" size={40} />
        <CatalogIcon assetId="challenge-birthday-week" icon="PARTY" alt="Birthday Week" size={40} />
      </div>
      <Button onClick={() => setBirthday(true)}>Show birthday example</Button>
    </section>
    <ArtworkShowcase />
    {detail && <BadgeDetailSheet entry={detail} onClose={() => setDetail(null)} />}
    {birthday && <BirthdayCelebrationModal entry={{ id: 9001, title: 'Turned 15', metadata: { gift_coins: 125 } }} onDismiss={() => setBirthday(false)} />}
  </main>;
}
createRoot(document.getElementById('root')).render(<Fixture />);
