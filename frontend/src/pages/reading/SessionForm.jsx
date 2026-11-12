import { useSpace } from '../../hooks/useSpace';
import { useState } from 'react';
import { createReadingSession, updateReadingSession } from '../../api';
import BottomSheet from '../../components/BottomSheet';
import ModalActions from '../../components/ModalActions';
import Button from '../../components/Button';
import ErrorAlert from '../../components/ErrorAlert';
import { TextField, SelectField, TextAreaField } from '../../components/form';
import { REACTIONS, REFLECTION_PROMPTS } from './reading.constants';
import useReadingSave from './useReadingSave';

export default function SessionForm({ session, books, selectedBook, today, adventure, userId, credential, onClose, onSaved }) {
  const { isParentAccount, isPersonalSpace } = useSpace();
  const personalParent = isParentAccount && isPersonalSpace;
  const initial = {
    book: String(session?.book ?? selectedBook?.id ?? ''), occurred_on: session?.occurred_on ?? today,
    duration_minutes: String(session?.duration_minutes ?? ''), pages_read: String(session?.pages_read ?? ''),
    section: session?.section ?? '', reflection: session?.reflection ?? '', format: session?.format ?? 'print', reaction: session?.reaction ?? '',
  };
  const [form, setForm] = useState(initial);
  const [prompt, setPrompt] = useState('');
  const { save, saving, uncertain, error, errors } = useReadingSave({ create: createReadingSession, update: updateReadingSession, existing: session, credential, onSaved });
  const change = (name) => (event) => setForm((value) => ({ ...value, [name]: event.target.value }));
  const bookTitle = session?.book_title ?? books.find((book) => String(book.id) === form.book)?.title;
  const hasReading = Number(form.duration_minutes) > 0 || Number(form.pages_read) > 0 || form.section.trim() || form.reflection.trim();
  return <BottomSheet title={session ? 'Edit reading log' : 'Log your reading'} onClose={onClose} disabled={saving} dirty={uncertain || JSON.stringify(form) !== JSON.stringify(initial)}>
    <form className="space-y-3" onSubmit={(event) => {
      event.preventDefault();
      if (!hasReading || !form.book) return;
      const payload = { ...form, duration_minutes: Number(form.duration_minutes || 0), pages_read: Number(form.pages_read || 0) };
      if (session) delete payload.book; else payload.book = Number(payload.book);
      if (!session && userId) payload.user_id = userId;
      void save(payload);
    }}>
      <ErrorAlert message={error} />
      {uncertain && <p role="status" className="text-body text-ink-secondary">We could not confirm the save. Retry safely with the same reading log; your words are still here.</p>}
      <fieldset disabled={saving || uncertain} className="space-y-3 min-w-0">
        {session ? <p className="font-bold text-ink-primary break-words">{bookTitle}</p> : <SelectField label="Which book?" value={form.book} onChange={change('book')} required error={errors.book}>
          <option value="">Choose a saved book</option>
          {books.map((book) => <option key={book.id} value={book.id}>{book.title}{book.author ? ` · ${book.author}` : ''}</option>)}
        </SelectField>}
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <TextField label="Date read" type="date" value={form.occurred_on} onChange={change('occurred_on')} max={today} required error={errors.occurred_on} />
          <SelectField label="How did you read?" value={form.format} onChange={change('format')} error={errors.format}>
            <option value="print">Print book</option><option value="ebook">Ebook</option><option value="audiobook">Audiobook</option>
          </SelectField>
          <TextField label="Minutes (optional)" type="number" min="0" max="600" step="1" value={form.duration_minutes} onChange={change('duration_minutes')} error={errors.duration_minutes} />
          <TextField label="Pages read (optional)" type="number" min="0" max="2000" step="1" value={form.pages_read} onChange={change('pages_read')} error={errors.pages_read} />
        </div>
        <TextField label="Chapter or section (optional)" value={form.section} onChange={change('section')} placeholder="For example, chapters 3–4" maxLength={120} error={errors.section} />
        <div className="rounded-xl bg-moss/10 p-3 space-y-3">
          <p className="text-body font-bold text-ink-primary">A little about what you read</p>
          <p className="text-caption text-ink-secondary">{personalParent ? 'Optional. These notes stay in your personal bookshelf.' : 'Optional. You and your parents can read these notes. For a private thought, use your Journal.'}</p>
          <div className="flex flex-wrap gap-2" aria-label="Reading reflection prompts">
            {REFLECTION_PROMPTS.map((value) => <Button key={value} variant="secondary" size="sm" aria-pressed={prompt === value} onClick={() => setPrompt(prompt === value ? '' : value)}>{value}</Button>)}
          </div>
          <TextAreaField label={prompt || 'Your reading note (optional)'} value={form.reflection} onChange={change('reflection')} rows={4} maxLength={3000} placeholder="A favorite moment, a new idea, or something you wondered…" error={errors.reflection} />
        </div>
        <SelectField label="How was it? (optional)" value={form.reaction} onChange={change('reaction')} error={errors.reaction}>
          {REACTIONS.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
        </SelectField>
      </fieldset>
      <p className="text-caption text-ink-secondary">Add minutes, pages, a chapter, or a reading note. Listening counts too.</p>
      {session ? <p className="text-caption text-ink-secondary">Editing a log does not add reward minutes or earn another reading reward.</p> : adventure && <p className="text-caption text-ink-secondary">{form.occurred_on !== today ? 'Earlier reading belongs in your history. Only new logs dated today count toward today’s reading reward.' : adventure.earned ? 'Today’s reading reward is already earned. You can keep logging without earning another reading reward today.' : `Log ${adventure.remaining_minutes} more ${adventure.remaining_minutes === 1 ? 'minute' : 'minutes'} today toward your reading reward. Audiobook minutes count too. Pages, chapters and notes can still be saved without minutes.`}</p>}
      <ModalActions onClose={onClose} saving={saving} submitLabel={uncertain ? 'Retry save' : session ? 'Save changes' : 'Save reading'} submitDisabled={!form.book || !hasReading} fullWidth />
    </form>
  </BottomSheet>;
}
