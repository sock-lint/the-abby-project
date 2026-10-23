import { createRoot } from 'react-dom/client';
import { MemoryRouter, useLocation } from 'react-router-dom';
import Hatchery from '../src/pages/bestiary/hatchery/Hatchery';
import { applyTheme } from '../src/themes';
import '../src/index.css';

const params = new URLSearchParams(window.location.search);
applyTheme(params.get('theme') || 'hyrule');
if (params.get('text') === '150') document.documentElement.style.fontSize = '150%';

export default function Fixture() {
  const location = useLocation();
  return <main className="max-w-6xl mx-auto p-4 space-y-4">
    <p className="text-caption text-ink-secondary">Local synthetic Hatchery review. No production accounts or reward writes.</p>
    <Hatchery />
    <output aria-label="Fixture location" className="block text-caption text-ink-secondary break-words">{location.pathname}{location.search}</output>
    <p className="text-caption text-ink-secondary">Missing private artwork keeps its labelled fallback. These checks do not establish artwork approval or physical-phone acceptance.</p>
  </main>;
}

createRoot(document.getElementById('root')).render(<MemoryRouter initialEntries={['/bestiary?tab=hatchery']}><Fixture /></MemoryRouter>);
