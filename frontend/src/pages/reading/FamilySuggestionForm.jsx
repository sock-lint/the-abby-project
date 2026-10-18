import { useState } from 'react';
import { createReadingFamilySuggestion } from '../../api';
import BottomSheet from '../../components/BottomSheet';
import ModalActions from '../../components/ModalActions';
import ErrorAlert from '../../components/ErrorAlert';
import { TextAreaField } from '../../components/form';
import useReadingSave from './useReadingSave';

export default function FamilySuggestionForm({ book, userId, credential, onSaved, onClose }) {
  const [message, setMessage] = useState('');
  const { save, saving, uncertain, error, errors } = useReadingSave({ create: createReadingFamilySuggestion, credential, onSaved });
  return <BottomSheet title="Send a book suggestion" onClose={onClose} disabled={saving} dirty={Boolean(message) || uncertain}>
    <form className="space-y-3" onSubmit={(event) => { event.preventDefault(); void save({ catalog_id: book.id, user_id: userId, message: message.trim() }); }}>
      <p className="text-body text-ink-primary"><strong>{book.title}</strong> by {book.author}</p>
      <p className="text-body text-ink-secondary">Your child chooses whether to save this book to their shelf.</p>
      <ErrorAlert message={error} />
      {uncertain && <p role="status" className="text-body text-ink-secondary">We could not confirm the suggestion. Retry safely before making changes.</p>}
      <TextAreaField label="Personal note (optional)" value={message} onChange={(event) => setMessage(event.target.value)} maxLength={500} disabled={saving || uncertain} error={errors.message} helpText={`${message.length}/500 characters`} rows={4} />
      <ModalActions onClose={onClose} cancelLabel="Cancel" saving={saving} submitLabel={uncertain ? 'Retry suggestion' : 'Send suggestion'} fullWidth />
    </form>
  </BottomSheet>;
}
