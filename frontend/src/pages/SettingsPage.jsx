import { useState, useEffect, useMemo, useRef } from 'react';
import { Link } from 'react-router-dom';
import {
  LogOut, Link2, Unlink, Calendar, RefreshCw, Flame, Check, Camera, Trash2,
  Lock,
} from 'lucide-react';
import {
  getGoogleAuthUrl, getGoogleAccount, unlinkGoogleAccount,
  updateCalendarSettings, triggerCalendarSync,
  uploadAvatar, removeAvatar,
  getCosmetics, equipCosmetic,
} from '../api';
import ParchmentCard from '../components/journal/ParchmentCard';
import RuneBadge from '../components/journal/RuneBadge';
import ConfirmDialog from '../components/ConfirmDialog';
import ErrorAlert from '../components/ErrorAlert';
import SectionHeader from '../components/SectionHeader';
import PageShell from '../components/layout/PageShell';
import { CoinIcon } from '../components/icons/JournalIcons';
import { useAuth } from '../hooks/useApi';
import { themes, applyTheme, LEGACY_THEME_ALIASES } from '../themes';
import { cosmeticLockHint } from './character/character.constants';
import { downscaleImage } from '../utils/image';
import Button from '../components/Button';
import InstallCard from '../pwa/InstallCard';

export default function SettingsPage() {
  const { user, logout: onLogout, setUser } = useAuth();
  const initialTheme = LEGACY_THEME_ALIASES[user?.theme] || user?.theme || 'hyrule';
  const [currentTheme, setCurrentTheme] = useState(initialTheme);

  // Owned journal covers, keyed by theme slug (e.g. ``hyrule``). The map
  // is built from the user's ``/api/cosmetics/`` active_theme slot —
  // legacy ``theme-*`` cosmetics without a ``metadata.theme`` linking to
  // a palette in themes.js are intentionally filtered out so the picker
  // only surfaces journal covers that actually swap the visible binding.
  const [ownedByTheme, setOwnedByTheme] = useState({});
  const [coversLoading, setCoversLoading] = useState(true);
  const [coverEquipping, setCoverEquipping] = useState(null); // theme slug
  const [coverError, setCoverError] = useState('');

  const [googleAccount, setGoogleAccount] = useState(null);
  const [googleLoading, setGoogleLoading] = useState(true);
  const [calendarEnabled, setCalendarEnabled] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [googleMessage, setGoogleMessage] = useState('');

  const avatarInputRef = useRef(null);
  const [avatarUploading, setAvatarUploading] = useState(false);
  const [avatarError, setAvatarError] = useState('');
  const [confirmRemoveAvatar, setConfirmRemoveAvatar] = useState(false);

  const handleAvatarPick = () => avatarInputRef.current?.click();

  const handleAvatarChange = async (e) => {
    const file = e.target.files?.[0];
    e.target.value = '';
    if (!file) return;
    setAvatarError('');
    setAvatarUploading(true);
    try {
      const processed = await downscaleImage(file, { maxDim: 512, quality: 0.9 });
      const updated = await uploadAvatar(processed);
      if (updated) setUser(updated);
    } catch (err) {
      setAvatarError(err.message || 'Upload failed');
    } finally {
      setAvatarUploading(false);
    }
  };

  const handleAvatarRemove = async () => {
    setConfirmRemoveAvatar(false);
    setAvatarError('');
    setAvatarUploading(true);
    try {
      const updated = await removeAvatar();
      if (updated) setUser(updated);
    } catch (err) {
      setAvatarError(err.message || 'Remove failed');
    } finally {
      setAvatarUploading(false);
    }
  };

  useEffect(() => {
    loadGoogleAccount();
    loadCovers();
    const params = new URLSearchParams(window.location.search);
    const googleStatus = params.get('google');
    if (googleStatus === 'linked') {
      setGoogleMessage('Google account linked successfully.');
      window.history.replaceState({}, '', window.location.pathname);
    } else if (googleStatus === 'error') {
      const detail = params.get('detail') || 'unknown';
      setGoogleMessage(`Google linking failed: ${detail}`);
      window.history.replaceState({}, '', window.location.pathname);
    }
  }, []);

  // Keep the picker's active swatch in lockstep with the auth user.
  // After equipping from the Frontispiece, the user's ``theme`` updates
  // via ``setUser`` — without this effect, navigating to Settings would
  // still show the previous cover as "reading".
  useEffect(() => {
    const resolved = LEGACY_THEME_ALIASES[user?.theme] || user?.theme;
    if (resolved && themes[resolved]) {
      setCurrentTheme(resolved);
    }
  }, [user?.theme]);

  const loadCovers = async () => {
    setCoversLoading(true);
    try {
      const data = await getCosmetics();
      const themeItems = Array.isArray(data?.active_theme) ? data.active_theme : [];
      const map = {};
      for (const item of themeItems) {
        const slug = item?.metadata?.theme;
        if (slug && themes[slug]) {
          map[slug] = item;
        }
      }
      setOwnedByTheme(map);
    } catch {
      // Best-effort — if cosmetics fail to load, picker degrades to
      // "everything locked" rather than rendering a half-broken UI.
      setOwnedByTheme({});
    } finally {
      setCoversLoading(false);
    }
  };

  const loadGoogleAccount = async () => {
    setGoogleLoading(true);
    try {
      const data = await getGoogleAccount();
      setGoogleAccount(data);
      if (data?.linked) setCalendarEnabled(data.calendar_sync_enabled || false);
    } catch {
      setGoogleAccount(null);
    } finally {
      setGoogleLoading(false);
    }
  };

  const handleThemeChange = async (themeName) => {
    const owned = ownedByTheme[themeName];
    if (!owned) return; // locked covers are non-interactive
    setCoverError('');
    setCoverEquipping(themeName);
    // Optimistic local swap so the swatch + page paint feel instant; we
    // roll back on equip failure.
    const prevTheme = currentTheme;
    setCurrentTheme(themeName);
    applyTheme(themeName);
    try {
      await equipCosmetic(owned.id);
      if (user) {
        setUser({
          ...user,
          theme: themeName,
          character_profile: user.character_profile
            ? { ...user.character_profile, active_theme_id: owned.id }
            : user.character_profile,
        });
      }
    } catch (err) {
      setCurrentTheme(prevTheme);
      applyTheme(prevTheme);
      setCoverError(err?.message || 'Failed to switch cover');
    } finally {
      setCoverEquipping(null);
    }
  };

  const handleLinkGoogle = async () => {
    try {
      const data = await getGoogleAuthUrl();
      if (data?.authorization_url) {
        window.location.href = data.authorization_url;
      }
    } catch {
      setGoogleMessage('Could not start Google linking.');
    }
  };

  const handleUnlinkGoogle = async () => {
    try {
      await unlinkGoogleAccount();
      setGoogleAccount({ linked: false });
      setCalendarEnabled(false);
      setGoogleMessage('Google account unlinked.');
    } catch {
      setGoogleMessage('Failed to unlink Google account.');
    }
  };

  const handleToggleCalendar = async () => {
    const newVal = !calendarEnabled;
    try {
      await updateCalendarSettings({ calendar_sync_enabled: newVal });
      setCalendarEnabled(newVal);
    } catch {
      setGoogleMessage('Failed to update calendar settings.');
    }
  };

  const handleSync = async () => {
    setSyncing(true);
    try {
      await triggerCalendarSync();
      setGoogleMessage('Calendar sync started.');
    } catch {
      setGoogleMessage('Failed to start sync.');
    } finally {
      setSyncing(false);
    }
  };

  const ownedCount = useMemo(
    () => Object.keys(themes).filter((key) => ownedByTheme[key]).length,
    [ownedByTheme],
  );

  const fieldLabel = 'font-script text-body text-ink-whisper';
  const fieldValue = 'font-body text-ink-primary';

  return (
    <PageShell width="narrow" rhythm="loose">
      <header>
        <div className="font-script text-sheikah-teal-deep text-base">
          preferences · tune the journal
        </div>
        <h1 className="font-display italic text-3xl md:text-4xl text-ink-primary leading-tight">
          Settings
        </h1>
      </header>

      {/* Profile */}
      <ParchmentCard>
        <SectionHeader index={0} title="Profile" kicker="who's keeping this journal" className="mb-4" />
        <div className="space-y-3">
          <div className="flex items-center gap-4">
            <div className="w-20 h-20 rounded-full bg-sheikah-teal/20 border border-sheikah-teal/40 flex items-center justify-center text-sheikah-teal-deep font-rune text-2xl overflow-hidden shrink-0">
              {user?.avatar ? (
                <img src={user.avatar} alt="" className="w-full h-full object-cover" />
              ) : (
                ((user?.display_name || user?.username || '?')[0] || '?').toUpperCase()
              )}
            </div>
            <div className="flex flex-col gap-2">
              <input
                ref={avatarInputRef}
                type="file"
                accept="image/png,image/jpeg,image/webp"
                onChange={handleAvatarChange}
                className="hidden"
                disabled={avatarUploading}
              />
              <Button
                size="sm"
                variant="secondary"
                onClick={handleAvatarPick}
                disabled={avatarUploading}
                className="flex items-center gap-1.5"
              >
                <Camera size={14} />
                {avatarUploading ? 'Saving…' : user?.avatar ? 'Change avatar' : 'Upload avatar'}
              </Button>
              {user?.avatar && (
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={() => setConfirmRemoveAvatar(true)}
                  disabled={avatarUploading}
                  className="flex items-center gap-1.5 text-ink-whisper"
                >
                  <Trash2 size={14} /> Remove
                </Button>
              )}
            </div>
          </div>
          {avatarError && <ErrorAlert message={avatarError} />}
          <div className="flex justify-between items-baseline text-body">
            <span className={fieldLabel}>Username</span>
            <span className={fieldValue}>{user?.username}</span>
          </div>
          <div className="flex justify-between items-baseline text-body">
            <span className={fieldLabel}>Display name</span>
            <span className={fieldValue}>{user?.display_name || '—'}</span>
          </div>
          <div className="flex justify-between items-baseline text-body">
            <span className={fieldLabel}>Role</span>
            <RuneBadge tone="teal" size="sm">{user?.role}</RuneBadge>
          </div>
          <div className="flex justify-between items-baseline text-body">
            <span className={fieldLabel}>Hourly rate</span>
            <span className="font-rune font-bold text-ink-primary tabular-nums">
              ${user?.hourly_rate}/hr
            </span>
          </div>
        </div>
      </ParchmentCard>

      {/* Use the inline check rather than ``useRole`` so we don't fork the
          ``useAuth`` context already destructured above for ``setUser`` /
          ``logout``. ``useRole`` is preferred when those aren't needed. */}
      {user?.role === 'parent' && user?.family && (
        <ParchmentCard>
          <SectionHeader index={1} title="Family" kicker="your household" className="mb-2" />
          <div className="font-display text-base text-ink-primary">
            {user.family.name}
          </div>
          <div className="font-script text-ink-whisper text-caption mt-1">
            chapter scoped to this household
          </div>
        </ParchmentCard>
      )}

      <InstallCard />

      {confirmRemoveAvatar && (
        <ConfirmDialog
          title="Remove your avatar?"
          message="Your circle will go back to your initial until you upload another."
          confirmLabel="Remove"
          onConfirm={handleAvatarRemove}
          onCancel={() => setConfirmRemoveAvatar(false)}
        />
      )}

      {/* Google */}
      <ParchmentCard>
        <SectionHeader index={2} title="Google account" kicker="connect a calendar" className="mb-4" />
        {googleMessage && (
          <div className="font-script text-body text-sheikah-teal-deep mb-3">{googleMessage}</div>
        )}
        {googleLoading ? (
          <div className="font-script text-body text-ink-whisper">Loading…</div>
        ) : googleAccount?.linked ? (
          <div className="space-y-3">
            <div className="flex justify-between items-center text-body">
              <span className={fieldLabel}>Linked to</span>
              <span className={fieldValue}>{googleAccount.google_email}</span>
            </div>
            <Button
              variant="ghost"
              size="sm"
              onClick={handleUnlinkGoogle}
              className="flex items-center gap-2 font-script text-body text-ember-deep hover:text-ember"
            >
              <Unlink size={14} /> unlink Google account
            </Button>
          </div>
        ) : (
          <Button
            variant="secondary"
            onClick={handleLinkGoogle}
            className="flex items-center gap-2 w-full"
          >
            <Link2 size={16} /> Connect Google account
          </Button>
        )}
      </ParchmentCard>

      {/* Calendar Sync */}
      {googleAccount?.linked && (
        <ParchmentCard>
          <SectionHeader index={3} title="Calendar sync" kicker="weave the dates in" className="mb-2" />
          <p className="font-body text-body text-ink-secondary mb-4">
            Sync project deadlines, chore schedules, and work sessions to your Google Calendar.
          </p>
          <div className="space-y-3">
            <label className="flex items-center justify-between cursor-pointer font-body text-body text-ink-primary">
              <span className="flex items-center gap-2">
                <Calendar size={16} className="text-sheikah-teal-deep" />
                Enable calendar sync
              </span>
              <button
                type="button"
                onClick={handleToggleCalendar}
                className={`relative w-10 h-5 rounded-full transition-colors ${
                  calendarEnabled ? 'bg-sheikah-teal-deep' : 'bg-ink-page-shadow'
                }`}
                aria-pressed={calendarEnabled}
              >
                <span
                  className={`absolute top-0.5 left-0.5 w-4 h-4 rounded-full bg-ink-page-rune-glow transition-transform ${
                    calendarEnabled ? 'translate-x-5' : ''
                  }`}
                />
              </button>
            </label>
            {calendarEnabled && (
              <Button
                variant="ghost"
                size="sm"
                onClick={handleSync}
                disabled={syncing}
                className="flex items-center gap-2 font-script text-body text-sheikah-teal-deep hover:text-sheikah-teal"
              >
                <RefreshCw size={14} className={syncing ? 'animate-spin' : ''} />
                {syncing ? 'syncing…' : 'sync now'}
              </Button>
            )}
          </div>
        </ParchmentCard>
      )}

      {/* Journal covers (themes) */}
      <ParchmentCard>
        <SectionHeader index={4} title="Journal cover" kicker="pick a cover" className="mb-2" />
        {coverError && <ErrorAlert message={coverError} className="mt-2" />}
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 mt-3" data-testid="cover-picker">
          {Object.entries(themes).map(([key, theme]) => {
            const owned = ownedByTheme[key];
            const active = owned && currentTheme === key;
            const equipping = coverEquipping === key;
            const t = theme.tones || {};

            if (!owned) {
              // Locked intaglio — mirrors the Frontispiece cosmetic
              // chapter so the "earning" ceremony reads consistently
              // across surfaces. Non-interactive, ``role="img"``.
              return (
                <div
                  key={key}
                  role="img"
                  aria-label={`${theme.name} cover · not yet earned`}
                  data-testid={`cover-locked-${key}`}
                  className="relative p-3 rounded-xl border-2 border-dashed border-ink-page-shadow text-left bg-ink-page-aged/60"
                  style={{ filter: 'grayscale(0.85)' }}
                >
                  <span
                    aria-hidden
                    className="absolute top-2 right-2 inline-flex items-center gap-1 px-1.5 py-0.5 rounded-full text-micro font-rune uppercase tracking-wider border border-ink-page-shadow bg-ink-page-aged text-ink-whisper"
                  >
                    <Lock size={10} strokeWidth={2.5} />
                    locked
                  </span>
                  <div className="flex items-baseline gap-2 opacity-70">
                    <div className="text-2xl leading-none" aria-hidden>{theme.icon}</div>
                    <div className="font-display text-base font-semibold leading-tight text-ink-whisper">
                      {theme.name}
                    </div>
                  </div>
                  <div className="font-script text-caption mt-2 italic leading-snug text-ink-whisper/80 line-clamp-2">
                    {cosmeticLockHint({ description: '', rarity: 'uncommon' })}
                  </div>
                </div>
              );
            }

            return (
              <button
                key={key}
                type="button"
                onClick={() => handleThemeChange(key)}
                disabled={coversLoading || equipping}
                aria-pressed={active}
                aria-label={`Pick ${theme.name} cover`}
                data-testid={`cover-owned-${key}`}
                className={`relative p-3 rounded-xl border-2 text-left transition-all disabled:opacity-70 ${
                  active
                    ? 'border-sheikah-teal-deep ring-2 ring-offset-2 ring-offset-ink-page ring-sheikah-teal-glow'
                    : 'border-ink-page-shadow hover:border-sheikah-teal/50'
                }`}
                style={{ backgroundColor: theme.page }}
              >
                {active && (
                  <span
                    className="absolute top-2 right-2 inline-flex items-center gap-1 px-1.5 py-0.5 rounded-full text-micro font-rune uppercase tracking-wider border"
                    style={{
                      color: theme.accent,
                      borderColor: theme.accent,
                      backgroundColor: theme.pageAged,
                    }}
                  >
                    <Check size={10} strokeWidth={2.5} />
                    reading
                  </span>
                )}
                <div className="flex items-baseline gap-2">
                  <div className="text-2xl leading-none" aria-hidden>{theme.icon}</div>
                  <div
                    className="font-display text-base font-semibold leading-tight"
                    style={{ color: theme.ink }}
                  >
                    {theme.name}
                  </div>
                </div>
                <div
                  className="font-body text-caption mt-1.5 leading-snug"
                  style={{ color: theme.inkSecondary }}
                >
                  Ink the day&apos;s deeds here.
                </div>
                <div
                  className="font-script text-caption mt-0.5"
                  style={{ color: theme.inkWhisper }}
                >
                  — 6 chapters opened
                </div>
                <div className="flex items-center gap-1.5 mt-2.5">
                  <span
                    className="inline-flex items-center gap-1 h-6 px-1.5 rounded-full border text-tiny font-rune tabular-nums"
                    style={{
                      color: t.emberDeep || theme.ember,
                      borderColor: theme.pageShadow,
                      backgroundColor: theme.pageAged,
                    }}
                  >
                    <Flame size={11} />
                    <span>7</span>
                  </span>
                  <span
                    className="inline-flex items-center gap-1 h-6 px-1.5 rounded-full border text-tiny font-rune tabular-nums"
                    style={{
                      color: t.goldLeaf,
                      borderColor: theme.pageShadow,
                      backgroundColor: theme.pageAged,
                    }}
                  >
                    <CoinIcon size={11} />
                    <span>142</span>
                  </span>
                  <span
                    className="inline-flex items-center h-6 px-1.5 rounded-full border text-tiny font-rune"
                    style={{
                      color: theme.accent,
                      borderColor: theme.pageShadow,
                      backgroundColor: theme.pageAged,
                    }}
                  >
                    quest
                  </span>
                </div>
              </button>
            );
          })}
        </div>
        <div className="mt-3 font-script text-caption text-ink-whisper">
          {ownedCount} of {Object.keys(themes).length} covers bound —{' '}
          <Link to="/sigil" className="underline decoration-dotted hover:text-sheikah-teal-deep">
            find more on your Frontispiece →
          </Link>
        </div>
      </ParchmentCard>

      {/* About */}
      <ParchmentCard>
        <SectionHeader index={5} title="About Hyrule Field Notes" className="mb-2" />
        <p className="font-body text-body text-ink-secondary">
          Chronicle ventures, duties, rituals, and study. Ink hours, earn XP, unlock
          skills, collect coins, and grow the party.
        </p>
      </ParchmentCard>

      {/* Sign off */}
      <ParchmentCard>
        <SectionHeader index={6} title="Account" className="mb-4" />
        <Button
          size="sm"
          onClick={onLogout}
          className="flex items-center justify-center gap-2 w-full"
        >
          <LogOut size={16} /> Sign off
        </Button>
      </ParchmentCard>
    </PageShell>
  );
}
