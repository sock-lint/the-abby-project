import { createRoot } from 'react-dom/client';
import { MemoryRouter } from 'react-router-dom';
import '../src/index.css';
import DesignShowcase from '../src/pages/__design';
import { applyTheme } from '../src/themes';

const params = new URLSearchParams(window.location.search);
applyTheme(params.get('theme') || 'hyrule');
const shell = params.get('shell') === '1';
createRoot(document.getElementById('root')).render(<MemoryRouter>
  {shell && <div data-journal-sticky-header="true" aria-hidden="true"
    style={{ position: 'fixed', top: 0, left: 0, right: 0, height: 80, zIndex: 30, background: 'var(--color-ink-page-aged)' }} />}
  <DesignShowcase />
  {shell && <div data-journal-bottom-nav="true" aria-hidden="true"
    style={{ position: 'fixed', bottom: 0, left: 0, right: 0, height: 64, zIndex: 30, background: 'var(--color-ink-page-aged)' }} />}
</MemoryRouter>);
