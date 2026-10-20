import { createRoot } from 'react-dom/client';
import { MemoryRouter } from 'react-router-dom';
import { AuthProvider } from '../src/hooks/useApi';
import Trials from '../src/pages/trials';
import { applyTheme } from '../src/themes';
import '../src/index.css';

applyTheme(new URLSearchParams(window.location.search).get('theme') || 'hyrule');
createRoot(document.getElementById('root')).render(
  <MemoryRouter initialEntries={['/quests?tab=trials']}><AuthProvider><main className="mx-auto max-w-7xl p-4"><Trials /></main></AuthProvider></MemoryRouter>,
);
