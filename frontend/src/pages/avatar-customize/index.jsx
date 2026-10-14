import { useSyncExternalStore } from 'react';
import { getAvatarCatalog, getCharacterProfile } from '../../api';
import { AUTH_CHANGED_EVENT, getToken } from '../../api/client';
import { useApi, useAuth } from '../../hooks/useApi';
import { STORAGE_KEYS } from '../../constants/storage';
import Button from '../../components/Button';
import ErrorAlert from '../../components/ErrorAlert';
import Loader from '../../components/Loader';
import PageShell from '../../components/layout/PageShell';
import AvatarEditor from './AvatarEditor';
import { resolveAvatarCatalog } from './catalog';

function subscribeCredential(callback) {
  const storage = (event) => { if (event.key === null || event.key === STORAGE_KEYS.AUTH_TOKEN) callback(); };
  window.addEventListener(AUTH_CHANGED_EVENT, callback);
  window.addEventListener('storage', storage);
  return () => {
    window.removeEventListener(AUTH_CHANGED_EVENT, callback);
    window.removeEventListener('storage', storage);
  };
}

function AvatarSession({ accountId, credential }) {
  const profile = useApi(getCharacterProfile);
  const catalog = useApi(getAvatarCatalog);
  if (profile.loading || catalog.loading) return <Loader />;
  const resolved = resolveAvatarCatalog(catalog.data);
  if (profile.error || catalog.error || !profile.data || !resolved) return <div className="space-y-3">
    <h1 className="font-body font-bold text-2xl text-ink-primary">Customize avatar</h1>
    <ErrorAlert message={profile.error || catalog.error || 'Avatar customization options are unavailable.'} />
    <Button variant="secondary" onClick={() => { profile.reload(); catalog.reload(); }}>Retry customization</Button>
  </div>;
  return <AvatarEditor catalog={resolved} initialConfiguration={profile.data.avatar_configuration ?? null} accountId={accountId} credential={credential} />;
}

export default function CustomizeAvatarPage() {
  const { user } = useAuth();
  const credential = useSyncExternalStore(subscribeCredential, getToken);
  return <PageShell width="wide" animate={false}>
    {user?.id && credential ? <AvatarSession key={`${user.id}:${credential}`} accountId={user.id} credential={credential} /> : <Loader />}
  </PageShell>;
}
