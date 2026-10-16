import { useState } from 'react';
import { createRoot } from 'react-dom/client';
import CompanionPreview from '../src/components/companion/CompanionPreview';
import Button from '../src/components/Button';
import '../src/index.css';

const chick = { id: 1, species: { slug: 'chick', name: 'Chick', sprite_key: 'cute-chick', icon: '🐤' }, potion: { name: 'Base', slug: 'base' }, growth_points: 35, evolution_stage: 'chick', evolved_to_mount: false, is_active: true };
export default function Fixture() {
  const [creature, setCreature] = useState(chick);
  return <main className="max-w-3xl mx-auto p-4 space-y-4">
    <h1 className="text-lede font-bold">Synthetic companion fixture</h1>
    <p>Private local art evaluation with synthetic ownership. No account or server rewards.</p>
    <div className="flex flex-wrap gap-2">
      <Button onClick={() => setCreature(chick)}>Use Chick</Button>
      <Button onClick={() => setCreature({ ...chick, growth_points: 50, evolution_stage: 'fledgling' })}>Use Fledgling</Button>
      <Button onClick={() => setCreature({ ...chick, growth_points: 100, evolution_stage: 'bird', evolved_to_mount: true })}>Use evolved Bird</Button>
      <Button onClick={() => setCreature({ ...chick, id: 2, species: { name: 'Fox', sprite_key: 'fox', icon: '🦊' } })}>Use Fox</Button>
    </div>
    <CompanionPreview creature={creature}><Button variant="secondary">Existing care controls</Button></CompanionPreview>
  </main>;
}
createRoot(document.getElementById('root')).render(<Fixture />);
