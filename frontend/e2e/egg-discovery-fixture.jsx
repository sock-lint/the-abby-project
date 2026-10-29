import { createRoot } from 'react-dom/client';
import { MemoryRouter, useLocation, useNavigate } from 'react-router-dom';
import { AuthProvider } from '../src/hooks/useApi';
import { getToken } from '../src/api/client';
import { SpaceContext } from '../src/providers/spaceContext';
import EggDiscoveryPanel from '../src/pages/trials/EggDiscoveryPanel';
import SessionForm from '../src/pages/reading/SessionForm';
import { applyTheme } from '../src/themes';
import '../src/index.css';

const params = new URLSearchParams(window.location.search);
const family = params.get('account') === 'family';
applyTheme(params.get('theme') || 'hyrule');
if (params.get('text') === '150') document.documentElement.style.fontSize = '150%';

export default function Fixture() {
  const location = useLocation();
  const navigate = useNavigate();
  const back = () => navigate('/quests?tab=trials');
  const reading = new URLSearchParams(location.search).get('tab') === 'reading';
  return <main className="max-w-5xl mx-auto p-4 space-y-4">
    <h1 className="text-lede font-bold text-ink-primary">Synthetic egg discovery review</h1>
    <p className="text-caption text-ink-secondary">Local fixture with synthetic accounts and intercepted APIs. No production access or private artwork.</p>
    {location.pathname === '/bestiary' ? <h2 className="text-lede font-semibold">Hatchery destination</h2>
      : reading ? <SessionForm books={[{ id: 1, title: 'Synthetic book' }]} selectedBook={{ id: 1 }} today="2026-10-29" credential={getToken()} onClose={back} onSaved={back} />
        : <EggDiscoveryPanel />}
    <output aria-label="Fixture location" className="block break-words text-caption text-ink-secondary">{location.pathname}{location.search}</output>
  </main>;
}

createRoot(document.getElementById('root')).render(
  <MemoryRouter initialEntries={['/quests?tab=trials']}><AuthProvider><SpaceContext.Provider value={{ space: family ? 'family' : 'personal', isFamilySpace: family, isPersonalSpace: !family, isParentAccount: family }}><Fixture /></SpaceContext.Provider></AuthProvider></MemoryRouter>,
);
