import { createRoot } from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';
import { AuthProvider } from '../src/hooks/useApi';
import ContentWorkbench from '../src/pages/manage/ContentWorkbench';
import { applyTheme } from '../src/themes';
import '../src/index.css';

applyTheme(new URLSearchParams(window.location.search).get('theme') || 'hyrule');
createRoot(document.getElementById('root')).render(<BrowserRouter><AuthProvider><main className="p-4"><ContentWorkbench /></main></AuthProvider></BrowserRouter>);
