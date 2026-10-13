import { useEffect, useState } from 'react';
import { createRoot } from 'react-dom/client';
import CompanionPreview from '../../src/components/companion/CompanionPreview';
import { inspectAssets } from './inspect';
import '../../src/index.css';

const manifests = import.meta.glob('../../src/companion/licensed/manifest.json', { eager: true, import: 'default' });
const manifest = manifests['../../src/companion/licensed/manifest.json'];
const chick = { catalog_available: true, id: 902, name: 'Private preview',
  species: { id: 941, slug: 'chick', name: 'Chick', sprite_key: 'cute-chick', icon: '🐤' },
  potion: { id: 942, slug: 'base', name: 'Base' }, growth_points: 80, evolved_to_mount: false,
  happiness_level: 'happy', is_active: true };
export default function Fixture() {
  const [status, setStatus] = useState('checking');
  const stage = new URLSearchParams(location.search).get('stage') === 'bird' ? 'bird' : 'chick';
  useEffect(() => {
    let active = true;
    inspectAssets(manifest).then((checks) => {
      if (active) { window.__ABBY_ASSET_CHECKS__ = checks; setStatus('passed'); }
    }).catch(() => { if (active) setStatus('failed'); });
    return () => { active = false; };
  }, []);
  return <main className="max-w-3xl mx-auto p-4 space-y-2">
    <h1 className="font-bold text-lede">Private asset evaluation</h1>
    <p className="text-caption">Synthetic child 901 · No account, credentials or rewards</p>
    <output data-testid="asset-inspection">{status}</output>
    <CompanionPreview creature={{ ...chick, evolved_to_mount: stage === 'bird' }} variant="primary">
      <button type="button">Synthetic care controls</button>
    </CompanionPreview>
  </main>;
}
createRoot(document.getElementById('root')).render(<Fixture />);
