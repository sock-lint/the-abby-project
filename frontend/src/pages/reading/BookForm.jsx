import { useState } from 'react';
import { createReadingBook, updateReadingBook } from '../../api';
import BottomSheet from '../../components/BottomSheet';
import ModalActions from '../../components/ModalActions';
import ErrorAlert from '../../components/ErrorAlert';
import { TextField, SelectField } from '../../components/form';
import { BOOK_STATUSES, READING_INTERESTS, labelFor } from './reading.constants';
import useReadingSave from './useReadingSave';

export default function BookForm({ book, suggestion, userId, credential, onClose, onSaved }) {
  const [title, setTitle] = useState(book?.title ?? suggestion?.title ?? '');
  const [author, setAuthor] = useState(book?.author ?? suggestion?.author ?? '');
  const [status, setStatus] = useState(book?.status ?? (suggestion ? 'want_to_read' : 'reading'));
  const [interests, setInterests] = useState(book?.interests ?? suggestion?.interests?.slice(0, 6) ?? []);
  const { save, saving, uncertain, error, errors } = useReadingSave({ create: createReadingBook, update: updateReadingBook, existing: book, credential, onSaved });
  const dirty = title !== (book?.title ?? suggestion?.title ?? '') || author !== (book?.author ?? suggestion?.author ?? '') || status !== (book?.status ?? (suggestion ? 'want_to_read' : 'reading')) || JSON.stringify(interests) !== JSON.stringify(book?.interests ?? suggestion?.interests?.slice(0, 6) ?? []);
  return <BottomSheet title={book ? 'Edit book' : 'Add a book'} onClose={onClose} disabled={saving} dirty={dirty || uncertain}>
    <form className="space-y-3" onSubmit={(event) => { event.preventDefault(); void save({ title: title.trim(), author: author.trim(), status, interests, ...(!book && userId ? { user_id: userId } : {}) }); }}>
      <ErrorAlert message={error} />
      {uncertain && <p role="status" className="text-body text-ink-secondary">We could not confirm the save. Retry this same book safely before making changes.</p>}
      <fieldset disabled={saving || uncertain} className="space-y-3 min-w-0">
        <TextField label="Book title" value={title} onChange={(event) => setTitle(event.target.value)} required maxLength={200} error={errors.title} autoComplete="off" />
        <TextField label="Author (optional)" value={author} onChange={(event) => setAuthor(event.target.value)} maxLength={160} error={errors.author} />
        <SelectField label="Shelf" value={status} onChange={(event) => setStatus(event.target.value)} error={errors.status}>
          {BOOK_STATUSES.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
        </SelectField>
        <fieldset className="space-y-2">
          <legend className="text-body font-bold text-ink-primary">What is it about? <span className="font-normal">(optional, up to 6)</span></legend>
          <div className="grid grid-cols-2 gap-2">
            {READING_INTERESTS.map((tag) => <label key={tag} className="flex min-h-11 items-center gap-2 rounded-xl border border-ink-page-shadow px-3 text-body text-ink-primary">
              <input type="checkbox" checked={interests.includes(tag)} disabled={!interests.includes(tag) && interests.length >= 6} onChange={(event) => setInterests(event.target.checked ? [...interests, tag] : interests.filter((value) => value !== tag))} className="accent-moss" />{labelFor(tag)}
            </label>)}
          </div>
          {errors.interests && <p role="alert" className="text-body text-ember-deep">{errors.interests}</p>}
        </fieldset>
      </fieldset>
      <ModalActions onClose={onClose} cancelLabel="Cancel" saving={saving} submitLabel={uncertain ? 'Retry save' : 'Save book'} fullWidth />
    </form>
  </BottomSheet>;
}
