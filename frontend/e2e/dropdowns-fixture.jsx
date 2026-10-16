import { useState } from 'react';
import { createRoot } from 'react-dom/client';
import { MemoryRouter } from 'react-router-dom';
import '../src/index.css';
import Button from '../src/components/Button';
import HomeworkFormModal from '../src/pages/Homework/HomeworkFormModal';
import { applyTheme } from '../src/themes';

applyTheme(new URLSearchParams(window.location.search).get('theme') || 'hyrule');
// These identities exist only in this local fixture. Playwright intercepts the
// real component's API write; no backend or stored credential is used.
const children = [
  { id: 21, username: 'synthetic-child', display_name: 'Alex' },
  { id: 22, username: 'synthetic-child-two', display_name: 'Morgan' },
  ...Array.from({ length: 18 }, (_, i) => ({ id: 30 + i, display_name: `Example child ${i + 1}` })),
];

export default function Fixture() {
  const [open, setOpen] = useState(false);
  const [saved, setSaved] = useState(false);
  return <MemoryRouter>
    <main className="p-4">
      <h1>Homework assignment dropdowns</h1>
      <Button onClick={() => setOpen(true)}>New assignment</Button>
      {saved && <p role="status">Assignment saved</p>}
      {open && <HomeworkFormModal isParent children={children}
        onClose={() => setOpen(false)}
        onSaved={() => { setSaved(true); setOpen(false); }} />}
    </main>
  </MemoryRouter>;
}

createRoot(document.getElementById('root')).render(<Fixture />);
