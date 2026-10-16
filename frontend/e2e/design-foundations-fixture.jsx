import { useState } from 'react';
import { createRoot } from 'react-dom/client';
import '../src/index.css';
import { applyTheme } from '../src/themes';
import PageShell from '../src/components/layout/PageShell';
import ParchmentCard from '../src/components/journal/ParchmentCard';
import ProgressBar from '../src/components/ProgressBar';
import Loader from '../src/components/Loader';
import BottomSheet from '../src/components/BottomSheet';
import Button from '../src/components/Button';
import ModalActions from '../src/components/ModalActions';
import { CheckboxField, DateField, SelectField, TextField, ToggleField } from '../src/components/form';
import SuccessToastProvider from '../src/components/SuccessToast';
import { useSuccessToast } from '../src/contexts/SuccessToastContext';
import ToastProvider from '../src/components/ToastManager';
import NotificationToast from '../src/components/NotificationToast';
import { useToastManager } from '../src/components/toast.context';
import { inkBleed } from '../src/motion/variants';

applyTheme(new URLSearchParams(window.location.search).get('theme') || 'hyrule');

export default function Fixture() {
  const [checked, setChecked] = useState(false);
  const [sheet, setSheet] = useState(false);
  const [note, setNote] = useState('');
  const [revision, setRevision] = useState(0);
  const showSuccess = useSuccessToast();
  const { push } = useToastManager();
  return <main className="p-4 max-w-3xl mx-auto space-y-4">
    <Button onClick={() => setRevision(revision + 1)}>Replay page</Button>
    <PageShell key={revision} variants={inkBleed} data-testid="page-reveal">
      <h1>Shared foundations</h1>
      <ParchmentCard tone="deep" data-testid="deep-surface">
        <p className="text-body text-ink-secondary">Secondary copy on a nested card</p>
        <p className="text-caption text-ink-whisper">Supporting caption on a nested card</p>
      </ParchmentCard>
      <ParchmentCard tone="deep" className="space-y-3">
        <TextField label="Example text" />
        <SelectField label="Example choice"><option>Choose</option></SelectField>
        <SelectField variant="filter" label="Choice filter"><option>All</option></SelectField>
        <DateField label="Example date" />
        <DateField variant="filter" label="From" />
        <CheckboxField label="Share with my family" checked={checked} onChange={(event) => setChecked(event.target.checked)} />
        <ToggleField label="Calendar sync" checked={checked} onChange={setChecked} />
      </ParchmentCard>
      <ProgressBar value={75} aria-label="Saved progress" />
      <Loader delayMs={0} />
    </PageShell>
    <Button onClick={() => showSuccess('Your changes are saved')}>Show success</Button>
    <Button onClick={() => push({ title: 'A saved update', message: 'Your changes are confirmed.', duration: 0 })}>Show general notification</Button>
    <section aria-label="Paired notification surfaces" className="space-y-3">
      {['neutral', 'success', 'danger', 'info', 'growth', 'treasure'].map((tone) => <NotificationToast
        key={tone} tone={tone} title={`${tone} notification`} message={`${tone} supporting copy`}
        onDismiss={() => {}}
      />)}
      {['common', 'uncommon', 'rare', 'epic', 'legendary'].map((rarity) => <NotificationToast
        key={rarity} rarity={rarity} title={`${rarity} earned item`} message={`${rarity} earned-item details`}
        onDismiss={() => {}}
      />)}
    </section>
    <Button onClick={() => setSheet(true)}>Open form</Button>
    {sheet && <BottomSheet
      title="A long form title that needs to wrap on a short phone screen"
      onClose={() => setSheet(false)} dirty={Boolean(note)}
      footer={<ModalActions formId="fixture-form" onClose={() => setSheet(false)} />}
    >
      <form id="fixture-form" onSubmit={(event) => { event.preventDefault(); setSheet(false); }}>
        <TextField label="Your note" value={note} onChange={(event) => setNote(event.target.value)} />
        <p className="min-h-64">Synthetic form content.</p>
      </form>
    </BottomSheet>}
  </main>;
}

createRoot(document.getElementById('root')).render(<SuccessToastProvider><ToastProvider><Fixture /></ToastProvider></SuccessToastProvider>);
