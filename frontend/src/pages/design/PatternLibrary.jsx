import { useContext, useState } from 'react';
import { Check, Plus, Trash2 } from 'lucide-react';
import Button from '../../components/Button';
import IconButton from '../../components/IconButton';
import BottomSheet from '../../components/BottomSheet';
import ConfirmDialog from '../../components/ConfirmDialog';
import ModalActions from '../../components/ModalActions';
import ErrorAlert from '../../components/ErrorAlert';
import EmptyState from '../../components/EmptyState';
import FilteredEmptyState from '../../components/FilteredEmptyState';
import ParchmentSkeleton from '../../components/ParchmentSkeleton';
import ParchmentCard from '../../components/journal/ParchmentCard';
import RuneBadge from '../../components/journal/RuneBadge';
import StatusBadge from '../../components/StatusBadge';
import SectionHeader from '../../components/SectionHeader';
import PageShell from '../../components/layout/PageShell';
import PageHeader from '../../components/layout/PageHeader';
import TabList from '../../components/layout/TabList';
import ProgressBar from '../../components/ProgressBar';
import NotificationToast from '../../components/NotificationToast';
import ChildContext from '../../components/family/ChildContext';
import AttachmentField from '../../components/attachments/AttachmentField';
import BadgeSigil from '../../components/atlas/BadgeSigil';
import IncipitBand from '../../components/atlas/IncipitBand';
import ChapterRubric from '../../components/atlas/ChapterRubric';
import RarityStrand from '../../components/atlas/RarityStrand';
import { RARITY_KEYS } from '../../components/atlas/mastery.constants';
import { TextField, TextAreaField, SelectField, DateField, CheckboxField, ToggleField, IconPicker } from '../../components/form';
import { DesignPreviewContext } from './preview.context';

function Specimen({ id, title, children, imports, guidance, consumers, status = 'Established' }) {
  return (
    <section id={id} aria-label={title} className="space-y-3 scroll-mt-4">
      <SectionHeader title={title} kicker={status} />
      {children}
      <details className="rounded-lg border border-ink-page-shadow px-3 text-body text-ink-secondary">
        <summary className="min-h-11 flex items-center cursor-pointer">Usage and existing consumers</summary>
        <p className="mb-2">{guidance}</p>
        <pre className="whitespace-pre-wrap break-all text-caption text-ink-primary">{imports}</pre>
        <ul className="space-y-1 py-3">
          {consumers.map(path => <li key={path}><a className="underline break-all" href={`https://github.com/sock-lint/the-abby-project/blob/main/frontend/src/${path}`}>{path}</a></li>)}
        </ul>
      </details>
    </section>
  );
}

function DataStates() {
  const [state, setState] = useState('ready');
  const { longContent } = useContext(DesignPreviewContext);
  const title = longContent ? 'Make a paper kite with a decorated tail and a sturdy frame for the whole family to try outdoors' : 'Make a paper kite';
  const content = <ParchmentCard><h3 className="font-bold text-body break-words">{title}</h3><p className="text-caption text-ink-secondary mt-2">Due tomorrow · Waiting for a parent to review</p></ParchmentCard>;
  return (
    <Specimen id="design-data" title="Data and feedback" imports={'import ErrorAlert from "../components/ErrorAlert";\nimport EmptyState from "../components/EmptyState";\nimport FilteredEmptyState from "../components/FilteredEmptyState";'} guidance="Keep failed reads separate from true emptiness. Preserve available content during refresh and identify which source failed. Clear filters without erasing saved data." consumers={['pages/Projects.jsx', 'pages/Habits.jsx', 'pages/Chores.jsx', 'pages/Inventory.jsx']}>
      <SelectField label="Data state" value={state} onChange={event => setState(event.target.value)}>
        <option value="ready">Loaded</option><option value="loading">Initial loading</option>
        <option value="refreshing">Refreshing existing content</option><option value="error">Failed read</option>
        <option value="empty">No saved items</option><option value="filtered">No filter matches</option>
        <option value="partial">Partially available</option>
      </SelectField>
      {state === 'loading' && <ParchmentSkeleton variant="list" count={2} />}
      {state === 'error' && <ErrorAlert message="Could not load activities. Your saved activities have not been removed." onRetry={() => setState('ready')} />}
      {state === 'empty' && <EmptyState action={<Button onClick={() => setState('ready')}>Create example activity</Button>}>No activities yet</EmptyState>}
      {state === 'filtered' && <FilteredEmptyState query="robotics" onClear={() => setState('ready')} />}
      {state === 'refreshing' && <p role="status" aria-live="polite" className="text-body text-ink-secondary">Refreshing activities. Showing the previous result.</p>}
      {state === 'partial' && <ErrorAlert message="Activities are available, but approval history could not load." onRetry={() => setState('ready')} />}
      {['ready', 'refreshing', 'partial'].includes(state) && content}
    </Specimen>
  );
}

function FormsAndDialogs() {
  const [open, setOpen] = useState(false);
  const [confirm, setConfirm] = useState(false);
  const [name, setName] = useState('');
  const [notes, setNotes] = useState('');
  const [shared, setShared] = useState(false);
  const [reminders, setReminders] = useState(true);
  const [saved, setSaved] = useState('');
  const [fieldError, setFieldError] = useState('');
  const [icon, setIcon] = useState('🎁');
  const { longContent } = useContext(DesignPreviewContext);
  const close = () => { setOpen(false); setName(''); setNotes(''); setFieldError(''); };
  const save = event => {
    event.preventDefault();
    if (!name.trim()) { setFieldError('Enter an activity name.'); return; }
    setSaved(`Example saved: ${name.trim()}`); close();
  };
  return (
    <Specimen id="design-forms" title="Forms and dialogs" imports={'import { TextField, DateField, CheckboxField, ToggleField, IconPicker } from "../components/form";\nimport BottomSheet from "../components/BottomSheet";\nimport ModalActions from "../components/ModalActions";'} guidance="Use shared labels, help and field errors. Route every dismiss affordance through the dirty/busy guard; restore focus to the opener. Disable repeated writes while submitting and keep failed input available. Editable emoji fields share IconPicker; choosing a preset updates local form state until Save." consumers={['pages/yearbook/JournalEntryFormModal.jsx', 'pages/grades/GradeEntryFormModal.jsx', 'pages/Homework/HomeworkFormModal.jsx', 'pages/Habits.jsx', 'pages/Chores.jsx', 'components/MovementSessionLogModal.jsx', 'pages/achievements/SkillFormModal.jsx']}>
      <ParchmentCard className="space-y-3">
        <IconPicker label="Example icon" value={icon} onChange={setIcon} placeholder="🎁" />
        <div className="grid sm:grid-cols-2 gap-3">
          <DateField label="Due date example" />
          <DateField label="Filter date example" variant="filter" />
        </div>
        <CheckboxField label="Share with parents in my family" checked={shared} onChange={event => setShared(event.target.checked)} helpText={shared ? 'Parents in your family can read this entry; siblings cannot.' : 'Only you can read this entry in the app.'} />
        <ToggleField label="Activity reminders" checked={reminders} onChange={setReminders} />
        <div className="flex flex-wrap items-center gap-3">
          <Button onClick={() => setOpen(true)}>Open example form</Button>
          <Button loading>Saving example</Button>
          <Button disabled variant="secondary">Unavailable action</Button>
          <IconButton aria-label="Delete example activity" variant="danger" onClick={() => setConfirm(true)}><Trash2 size={18} /></IconButton>
        </div>
        {saved && <p role="status" aria-live="polite" className="text-body text-moss-deep break-words">{saved}</p>}
      </ParchmentCard>
      {open && <BottomSheet title="Edit activity" onClose={close} dirty={Boolean(name || notes)} footer={<ModalActions onClose={close} cancelLabel="Discard example" submitLabel="Save example" formId="design-example-form" />}>
        <form id="design-example-form" onSubmit={save} className="space-y-3">
          <TextField label="Activity name" value={name} onChange={event => { setName(event.target.value); setFieldError(''); }} error={fieldError} autoFocus />
          <TextAreaField label="Notes" rows={3} value={notes} onChange={event => setNotes(event.target.value)} placeholder={longContent ? 'Long instructions and notes wrap beside the controls and remain readable on a short phone screen.' : 'What would help you get started?'} />
          <p className="text-caption text-ink-secondary">This example saves only local preview state. Escape or the close button checks for unsaved changes.</p>
        </form>
      </BottomSheet>}
      {confirm && <ConfirmDialog title={longContent ? 'Delete the activity with the unusually long title that needs to wrap on a small phone?' : 'Delete example activity?'} message="This local demonstration does not delete account data." onCancel={() => setConfirm(false)} onConfirm={() => { setSaved('Example deletion confirmed.'); setConfirm(false); }} />}
    </Specimen>
  );
}

function PageRecipes() {
  const [recipe, setRecipe] = useState('utility');
  const { role, longContent } = useContext(DesignPreviewContext);
  const tabs = [{ id: 'utility', label: 'Utility page' }, { id: 'dashboard', label: 'Dashboard' }, { id: 'collection', label: 'Collection' }];
  return (
    <Specimen id="design-recipes" title="Page recipes" imports={'import PageShell from "../components/layout/PageShell";\nimport PageHeader from "../components/layout/PageHeader";\nimport SectionHeader from "../components/SectionHeader";\nimport TabList from "../components/layout/TabList";'} guidance="Keep utility pages clear and compact. Compose collections and progression with Meadow accents. Give each actual page one accessible title, and let header actions wrap on phones." consumers={['pages/SettingsPage.jsx', 'pages/Manage.jsx', 'pages/ParentDashboard.jsx', 'pages/ChildDashboard.jsx', 'pages/Badges.jsx']}>
      <TabList tabs={tabs} activeId={recipe} onSelect={setRecipe} ariaLabel="Page recipe" />
      <ParchmentCard><PageShell animate={false} rhythm="tight">
        <PageHeader as="h3" title={recipe === 'utility' ? 'Settings' : recipe === 'dashboard' ? `${role === 'parent' ? 'Family' : 'Your'} today` : 'Badge collection'} kicker="Synthetic page example" actions={<Button variant="secondary"><Plus size={16} aria-hidden="true" /> {longContent ? 'Add an activity for the upcoming family weekend' : 'Add activity'}</Button>} />
        {recipe === 'dashboard' && <p className="text-body text-ink-secondary">{role === 'parent' ? 'Two activities are waiting for your review. Each row names the child and the next action.' : 'Choose one activity for today. Optional ideas stay below the important tasks.'}</p>}
        {recipe === 'collection' && <><ProgressBar value={3} max={8} aria-label="Example badge collection: 3 of 8 earned" /><p className="text-caption text-ink-secondary">3 of 8 earned · Counts come from the supported collection.</p></>}
        <SectionHeader as="h4" title={recipe === 'utility' ? 'Preferences' : recipe === 'collection' ? 'Recently earned' : 'Next activity'} />
        <p className="text-body text-ink-primary break-words">{longContent ? 'A long activity title remains readable without hiding the information needed to decide what to do next.' : 'Make a paper kite'}</p>
      </PageShell></ParchmentCard>
    </Specimen>
  );
}

function OutcomeExamples() {
  return (
    <Specimen id="design-outcomes" title="Status and outcomes" imports={'import StatusBadge from "../components/StatusBadge";\nimport RuneBadge from "../components/journal/RuneBadge";'} guidance="Workflow labels describe saved server state; rarity describes catalog tiers. Ownership and availability remain separate. Confirm saved work before displaying rewards, and keep uncertain saves recoverable." consumers={['pages/Homework/AssignmentCard.jsx', 'pages/Timecards.jsx', 'pages/Inventory.jsx', 'pages/Movement.jsx']}>
      <div className="grid sm:grid-cols-2 gap-3">
        <ParchmentCard className="space-y-3"><h3 className="font-bold text-body">Workflow</h3><div className="flex flex-wrap gap-2"><StatusBadge status="pending" /><StatusBadge status="approved" /><StatusBadge status="rejected" /><StatusBadge status="paid" /></div><p className="text-caption text-ink-secondary">Submitted does not mean approved or paid.</p></ParchmentCard>
        <ParchmentCard className="space-y-3"><h3 className="font-bold text-body">Rarity and availability</h3><RuneBadge tone="royal">Rare</RuneBadge><p className="text-body text-ink-primary">Saved collection · New acquisition unavailable</p><p className="text-caption text-ink-secondary">Retained ownership stays readable; artwork never grants eligibility.</p></ParchmentCard>
        <ParchmentCard className="space-y-3"><h3 className="font-bold text-body flex items-center gap-2"><Check size={18} aria-hidden="true" />Confirmed outcome</h3><p className="text-body">Session recorded · 0 XP earned</p><p className="text-caption text-ink-secondary">Record the activity even when no reward is due. Show XP only from a confirmed receipt.</p></ParchmentCard>
        <ParchmentCard className="space-y-3"><h3 className="font-bold text-body">Connectivity and saving</h3><p className="text-body">Draft on this device</p><p className="text-body">Save not confirmed · Check save</p><p className="text-caption text-ink-secondary">The app shell can open offline. Private data and server actions need a connection; a device draft is not a server receipt.</p></ParchmentCard>
      </div>
    </Specimen>
  );
}

function FamilyExamples() {
  const { role, longContent } = useContext(DesignPreviewContext);
  const [child, setChild] = useState('9001');
  const options = [{ id: 9001, display_name: longContent ? 'Alex with a long display name that remains readable' : 'Alex' }, { id: 9002, display_name: 'Sam' }];
  return <Specimen id="design-family" title="Family context and setup" imports={'import ChildContext from "../components/family/ChildContext";\nimport useChildContext from "../hooks/useChildContext";'} guidance="Use a verified current-family roster before accepting a child ID from a URL or remembered choice. Parents see only shared journal and grade entries. Setup confirms a saved username and offers an optional next activity without storing or displaying passwords." consumers={['pages/chronicle/JournalReader.jsx', 'pages/grades/GradesPage.jsx', 'pages/Yearbook.jsx', 'pages/Manage.jsx']}>
    <ParchmentCard className="space-y-3">
      {role === 'parent' ? <ChildContext children={options} selectedChildId={child} onSelect={setChild} /> : <p className="text-body text-ink-primary">You are viewing your own memories.</p>}
      <p className="text-body text-ink-secondary">Only me · Shared with parents</p>
      <p className="text-caption text-ink-secondary">Sharing lets parents in the family read and respond. Siblings cannot read the entry.</p>
    </ParchmentCard>
    <ParchmentCard className="space-y-3"><h3 className="font-bold text-body">Child account created · synthetic example</h3><p className="text-body">Sign-in name: <strong>sam.example</strong></p><p className="text-caption text-ink-secondary">Open Abby on the child’s device and sign in with this username and the password you chose. On a shared device, use a separate browser profile to keep accounts separate.</p><p className="text-body text-ink-primary">Next optional step: assign one homework activity.</p></ParchmentCard>
  </Specimen>;
}

function NotificationExamples() {
  const { longContent } = useContext(DesignPreviewContext);
  const [dismissed, setDismissed] = useState([]);
  const tones = ['neutral', 'success', 'danger', 'info', 'growth', 'treasure'];
  return <Specimen id="design-notifications" title="Notifications" imports={'import NotificationToast from "../components/NotificationToast";'} guidance="Pair notification foregrounds with their surfaces on every cover. Status tones and earned-item rarity are separate. Keep reward receipts, expiry and navigation in the owning domain; reduced motion must not prevent dismissal or expiration." consumers={['components/SuccessToast.jsx', 'components/ApprovalToastStack.jsx', 'components/DropToastStack.jsx', 'components/ExpeditionToastStack.jsx']}>
    <div className="grid sm:grid-cols-2 gap-3">
      {tones.filter(tone => !dismissed.includes(tone)).map(tone => <NotificationToast key={tone} tone={tone} title={`${tone[0].toUpperCase()}${tone.slice(1)} example`} message={longContent ? 'A longer notification summary wraps beside its dismissal control. The saved result remains available in its owning screen.' : 'Synthetic notification; no account data changed.'} onDismiss={() => setDismissed(items => [...items, tone])} swipe={false} role="group" aria-label={`${tone} notification example`} />)}
      <NotificationToast rarity="rare" title="Rare item example" message="An earned-item presentation uses its fixed rarity palette." swipe={false} />
    </div>
    {dismissed.length > 0 && <Button variant="secondary" onClick={() => setDismissed([])}>Restore notification examples</Button>}
  </Specimen>;
}

function AttachmentExample() {
  const [file, setFile] = useState(null);
  const [error, setError] = useState('');
  return <Specimen id="design-attachments" title="Attachments" imports={'import AttachmentField from "../components/attachments/AttachmentField";'} guidance="File selection, replacement and removal stay local until explicit submission. Keep selected files and entered text after a failed upload. The owning form supplies actual accepted formats and validation; do not invent size limits or progress percentages." consumers={['pages/Portfolio.jsx', 'pages/forge/PrintRequestModal.jsx']}>
    <ParchmentCard className="space-y-3">
      <AttachmentField label="Example photo" file={file} onChange={next => { setFile(next); setError(''); }} accept="image/*" previewImage helpText="Local image preview only. This example never uploads the file." error={error} />
      {file && <Button variant="secondary" onClick={() => setError('Example upload could not finish. Your selected file is still available for an explicit retry.')}>Preview upload failure</Button>}
    </ParchmentCard>
  </Specimen>;
}

function AtlasExamples() {
  const { longContent } = useContext(DesignPreviewContext);
  const [hints, setHints] = useState(true);
  const [selection, setSelection] = useState(null);
  const counts = Object.fromEntries(RARITY_KEYS.map((rarity, index) => [rarity, { earned: index % 3, total: 3 }]));
  const suffix = longContent ? ' for taking time to learn, practice and share a creative family activity' : '';
  const badgeName = rarity => `${rarity[0].toUpperCase()}${rarity.slice(1)} example badge${suffix}`;
  return <Specimen id="design-atlas" title="Atlas primitives" imports={'import BadgeSigil from "../components/atlas/BadgeSigil";\nimport IncipitBand from "../components/atlas/IncipitBand";\nimport ChapterRubric from "../components/atlas/ChapterRubric";\nimport RarityStrand from "../components/atlas/RarityStrand";\n\n<BadgeSigil badge={badge} earned={earned} hint={unlockHint} onSelect={setPreview} />\n<IncipitBand as="h4" letter="B" title="Badge collection" progressPct={27} rarityCounts={counts} />\n<ChapterRubric index={0} name="Activities" icon="✦" summary={{ level: 2, total_xp: 1200 }} />\n<ChapterRubric index={1} subject={subject} />\n<RarityStrand counts={counts} compact />'} guidance="Reuse these collection and progress primitives with domain-supplied names, hints and server-confirmed counts. Selecting a synthetic badge here only updates the local preview; it cannot earn a badge or grant XP. Earned badges suppress unlock hints. IncipitBand defaults to h1; set as to the heading level required by the surrounding page. ChapterRubric accepts direct name/icon/summary props or a legacy subject; direct props take precedence. RarityStrand accepts earned/total counts by rarity, with an accessible summary even when empty." consumers={['pages/achievements/CollectionFolio.jsx', 'pages/achievements/SigilCodex.jsx', 'pages/yearbook/ChapterCard.jsx', 'pages/Projects.jsx', 'pages/achievements/FolioSpread.jsx', 'pages/character/CosmeticChapter.jsx']}>
    <div className="space-y-3">
      <h3 className="font-display text-lede font-bold text-ink-primary">Badge tiles</h3>
      <p className="text-body text-ink-secondary">All five rarities, earned and locked. Toggle hints to compare caller-supplied guidance.</p>
      <CheckboxField label="Show badge unlock hints" checked={hints} onChange={event => setHints(event.target.checked)} />
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-4">
        {RARITY_KEYS.map(rarity => {
          const badge = { id: `design-${rarity}`, name: badgeName(rarity), rarity, icon: '✦', xp_bonus: 25 };
          return <div key={rarity} className="min-w-0 space-y-3">
            <BadgeSigil badge={badge} earned earnedAt="2020-01-01T12:00:00Z" hint={hints ? 'Example unlock guidance' : ''} onSelect={setSelection} />
            <BadgeSigil badge={badge} earned={false} hint={hints ? `Practice an example activity${suffix}.` : ''} onSelect={setSelection} />
          </div>;
        })}
      </div>
      <p role="status" aria-label="Badge selection" aria-live="polite" className="text-body text-ink-secondary break-words">{selection ? `Selected preview: ${selection.badge.name} · ${selection.badge.rarity} · ${selection.earned ? 'earned' : 'not yet earned'}.` : 'Choose an example badge to preview its selection.'}</p>
    </div>
    <div className="space-y-3">
      <h3 className="font-display text-lede font-bold text-ink-primary">Chapter openers</h3>
      <IncipitBand as="h4" letter="B" title={`Bare chapter example${suffix}`} />
      <IncipitBand as="h4" letter="K" title={`Kicker chapter example${suffix}`} kicker="Current chapter" meta="Synthetic dates · 2025–2026" progressPct={45} />
      <IncipitBand as="h4" letter="R" title={`Rarity chapter example${suffix}`} kicker="Example collection" meta="4 of 15 collected" progressPct={27} rarityCounts={counts} />
    </div>
    <ParchmentCard className="space-y-3">
      <p className="text-body text-ink-secondary">Chapter headings: direct props and the legacy subject shape, with and without summaries.</p>
      <ChapterRubric index={0} name={`Direct chapter heading${suffix}`} icon="✦" />
      <ChapterRubric index={1} name={`Direct heading with summary${suffix}`} icon="✦" summary={{ level: 2, total_xp: 1200 }} />
      <ChapterRubric index={2} subject={{ name: `Legacy subject heading${suffix}`, icon: '✦' }} />
      <ChapterRubric index={3} subject={{ name: `Legacy subject with summary${suffix}`, icon: '✦', summary: { level: 3, total_xp: 2400 } }} />
    </ParchmentCard>
    <ParchmentCard className="space-y-4">
      <h3 className="font-display text-lede font-bold text-ink-primary">Rarity summaries</h3>
      {[false, true].map(compact => <div key={String(compact)} className="space-y-2">
        <p className="text-body text-ink-secondary">{compact ? 'Compact height' : 'Default height'} · full counts</p>
        <RarityStrand counts={counts} compact={compact} />
        <p className="text-body text-ink-secondary">{compact ? 'Compact height' : 'Default height'} · empty counts</p>
        <RarityStrand counts={{}} compact={compact} />
      </div>)}
    </ParchmentCard>
  </Specimen>;
}

export default function PatternLibrary() {
  return <div className="space-y-10"><DataStates /><FormsAndDialogs /><PageRecipes /><OutcomeExamples /><FamilyExamples /><NotificationExamples /><AttachmentExample /><AtlasExamples /></div>;
}
