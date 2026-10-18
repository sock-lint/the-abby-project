import { createRoot } from 'react-dom/client';
import { MemoryRouter } from 'react-router-dom';
import '../src/index.css';
import { applyTheme } from '../src/themes';
import { AuthProvider } from '../src/hooks/useApi';
import ProgressionLab from '../src/pages/manage/ProgressionLab';

applyTheme('hyrule');

createRoot(document.getElementById('root')).render(
  <MemoryRouter initialEntries={['/manage/progression-lab']}>
    <AuthProvider><main className="p-4"><ProgressionLab /></main></AuthProvider>
  </MemoryRouter>,
);
