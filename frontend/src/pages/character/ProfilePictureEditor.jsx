import { useEffect, useRef, useState } from 'react';
import { Camera, Trash2 } from 'lucide-react';
import { uploadAvatar, removeAvatar } from '../../api';
import { getToken } from '../../api/client';
import { useAuth } from '../../hooks/useApi';
import { downscaleImage } from '../../utils/image';
import Button from '../../components/Button';
import ConfirmDialog from '../../components/ConfirmDialog';
import ErrorAlert from '../../components/ErrorAlert';

export default function ProfilePictureEditor() {
  const { user, setUser } = useAuth();
  const inputRef = useRef(null);
  const mounted = useRef(true);
  const activeIdentity = useRef(user?.id);
  activeIdentity.current = user?.id;
  const [working, setWorking] = useState(false);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const [confirmRemove, setConfirmRemove] = useState(false);

  useEffect(() => {
    mounted.current = true;
    return () => { mounted.current = false; };
  }, []);

  const isCurrent = (identity, token) => mounted.current
    && activeIdentity.current === identity && getToken() === token;

  const savePicture = async (file) => {
    const identity = user?.id;
    const token = getToken();
    setWorking(true);
    setError('');
    setMessage('');
    try {
      let updated;
      if (file) {
        const processed = await downscaleImage(file, { maxDim: 512, quality: 0.9 });
        // Image processing can finish after an account change. Do not upload
        // the previous account's picture with the new account's credential.
        if (!isCurrent(identity, token)) return;
        updated = await uploadAvatar(processed);
      } else {
        updated = await removeAvatar();
      }
      if (!isCurrent(identity, token)) return;
      if (updated) setUser((current) => current?.id === identity && getToken() === token
        ? { ...current, avatar: updated.avatar } : current);
      setMessage(file ? 'Profile picture saved.' : 'Profile picture removed.');
    } catch (error) {
      if (isCurrent(identity, token)) setError(error.message || 'Could not save your profile picture. Try again.');
    } finally {
      if (isCurrent(identity, token)) setWorking(false);
    }
  };

  const changePicture = (event) => {
    const file = event.target.files?.[0];
    event.target.value = '';
    if (file) void savePicture(file);
  };

  return (
    <section className="mt-3 space-y-2" aria-label="Profile picture">
      <p className="font-body text-caption text-ink-secondary">Your profile picture appears here and in navigation.</p>
      {/* The native file input is hidden behind the labelled upload button. */}
      <input ref={inputRef} type="file" accept="image/png,image/jpeg,image/webp"
        aria-label="Upload profile picture" onChange={changePicture} className="hidden" disabled={working || !user?.id} />
      <div className="flex flex-wrap gap-2">
        <Button size="sm" variant="secondary" className="inline-flex items-center gap-1.5" disabled={working || !user?.id} onClick={() => inputRef.current?.click()}>
          <Camera size={14} aria-hidden="true" /> {working ? 'Saving…' : user?.avatar ? 'Change picture' : 'Upload picture'}
        </Button>
        {user?.avatar && <Button size="sm" variant="ghost" className="inline-flex items-center gap-1.5" disabled={working} onClick={() => setConfirmRemove(true)}>
          <Trash2 size={14} aria-hidden="true" /> Remove picture
        </Button>}
      </div>
      <ErrorAlert message={error} />
      {message && <p className="font-body text-caption text-moss-deep" role="status">{message}</p>}
      {confirmRemove && <ConfirmDialog title="Remove profile picture?"
        message="Your initial will appear in its place. Your character will stay the same."
        confirmLabel="Remove picture" onCancel={() => setConfirmRemove(false)}
        onConfirm={() => { setConfirmRemove(false); void savePicture(null); }} />}
    </section>
  );
}
