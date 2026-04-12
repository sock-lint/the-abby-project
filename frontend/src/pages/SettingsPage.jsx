import { useState, useEffect } from 'react';
import { LogOut, Link2, Unlink, Calendar, RefreshCw } from 'lucide-react';
import { api } from '../api/client';
import {
  getGoogleAuthUrl, getGoogleAccount, unlinkGoogleAccount,
  updateCalendarSettings, triggerCalendarSync,
} from '../api';
import Card from '../components/Card';
import { themes, applyTheme } from '../themes';

export default function SettingsPage({ user, onLogout }) {
  const [currentTheme, setCurrentTheme] = useState(user?.theme || 'summer');

  // Google account state
  const [googleAccount, setGoogleAccount] = useState(null);
  const [googleLoading, setGoogleLoading] = useState(true);
  const [calendarEnabled, setCalendarEnabled] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [googleMessage, setGoogleMessage] = useState('');

  useEffect(() => {
    loadGoogleAccount();

    // Check for google link/error query params from OAuth callback
    const params = new URLSearchParams(window.location.search);
    const googleStatus = params.get('google');
    if (googleStatus === 'linked') {
      setGoogleMessage('Google account linked successfully!');
      window.history.replaceState({}, '', window.location.pathname);
    } else if (googleStatus === 'error') {
      const detail = params.get('detail') || 'unknown';
      setGoogleMessage(`Google linking failed: ${detail}`);
      window.history.replaceState({}, '', window.location.pathname);
    }
  }, []);

  const loadGoogleAccount = async () => {
    setGoogleLoading(true);
    try {
      const data = await getGoogleAccount();
      setGoogleAccount(data);
      if (data?.linked) {
        setCalendarEnabled(data.calendar_sync_enabled || false);
      }
    } catch { /* not linked */
      setGoogleAccount(null);
    } finally {
      setGoogleLoading(false);
    }
  };

  const handleThemeChange = async (themeName) => {
    setCurrentTheme(themeName);
    applyTheme(themeName);
    try {
      await api.patch(`/auth/me/`, { theme: themeName });
    } catch { /* best-effort */ }
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
      setGoogleMessage('Calendar sync started!');
    } catch {
      setGoogleMessage('Failed to start sync.');
    } finally {
      setSyncing(false);
    }
  };

  return (
    <div className="max-w-lg mx-auto space-y-6">
      <h1 className="font-heading text-2xl font-bold">Settings</h1>

      <Card>
        <h2 className="font-heading text-lg font-bold mb-4">Profile</h2>
        <div className="space-y-3">
          <div className="flex justify-between text-sm">
            <span className="text-forge-text-dim">Username</span>
            <span>{user?.username}</span>
          </div>
          <div className="flex justify-between text-sm">
            <span className="text-forge-text-dim">Display Name</span>
            <span>{user?.display_name || '\u2014'}</span>
          </div>
          <div className="flex justify-between text-sm">
            <span className="text-forge-text-dim">Role</span>
            <span className="capitalize">{user?.role}</span>
          </div>
          <div className="flex justify-between text-sm">
            <span className="text-forge-text-dim">Hourly Rate</span>
            <span className="font-heading font-bold">${user?.hourly_rate}/hr</span>
          </div>
        </div>
      </Card>

      {/* Google Account */}
      <Card>
        <h2 className="font-heading text-lg font-bold mb-4">Google Account</h2>
        {googleMessage && (
          <div className="text-sm text-amber-highlight mb-3">{googleMessage}</div>
        )}
        {googleLoading ? (
          <div className="text-sm text-forge-text-dim">Loading...</div>
        ) : googleAccount?.linked ? (
          <div className="space-y-3">
            <div className="flex justify-between items-center text-sm">
              <span className="text-forge-text-dim">Linked to</span>
              <span>{googleAccount.google_email}</span>
            </div>
            <button
              onClick={handleUnlinkGoogle}
              className="flex items-center gap-2 text-sm text-red-400 hover:text-red-300 transition-colors"
            >
              <Unlink size={14} /> Unlink Google Account
            </button>
          </div>
        ) : (
          <button
            onClick={handleLinkGoogle}
            className="flex items-center gap-2 w-full px-4 py-2.5 rounded-lg border border-forge-border text-forge-text hover:border-amber-primary/50 hover:text-amber-highlight transition-colors text-sm"
          >
            <Link2 size={16} /> Connect Google Account
          </button>
        )}
      </Card>

      {/* Calendar Sync (only if Google linked) */}
      {googleAccount?.linked && (
        <Card>
          <h2 className="font-heading text-lg font-bold mb-4">Calendar Sync</h2>
          <p className="text-xs text-forge-text-dim mb-4">
            Sync project deadlines, chore schedules, and work sessions to your Google Calendar.
          </p>
          <div className="space-y-3">
            <label className="flex items-center justify-between cursor-pointer">
              <span className="text-sm flex items-center gap-2">
                <Calendar size={16} className="text-forge-text-dim" />
                Enable calendar sync
              </span>
              <button
                onClick={handleToggleCalendar}
                className={`relative w-10 h-5 rounded-full transition-colors ${
                  calendarEnabled ? 'bg-amber-primary' : 'bg-forge-muted'
                }`}
              >
                <span
                  className={`absolute top-0.5 left-0.5 w-4 h-4 rounded-full bg-white transition-transform ${
                    calendarEnabled ? 'translate-x-5' : ''
                  }`}
                />
              </button>
            </label>
            {calendarEnabled && (
              <button
                onClick={handleSync}
                disabled={syncing}
                className="flex items-center gap-2 text-sm text-amber-highlight hover:text-amber-primary transition-colors disabled:opacity-50"
              >
                <RefreshCw size={14} className={syncing ? 'animate-spin' : ''} />
                {syncing ? 'Syncing...' : 'Sync Now'}
              </button>
            )}
          </div>
        </Card>
      )}

      <Card>
        <h2 className="font-heading text-lg font-bold mb-4">Theme</h2>
        <div className="grid grid-cols-2 gap-3">
          {Object.entries(themes).map(([key, theme]) => (
            <button
              key={key}
              onClick={() => handleThemeChange(key)}
              className={`p-3 rounded-xl border-2 text-left transition-all ${
                currentTheme === key
                  ? 'border-amber-primary'
                  : 'border-forge-border hover:border-forge-muted'
              }`}
              style={{ backgroundColor: theme.bg }}
            >
              <div className="text-2xl mb-1">{theme.icon}</div>
              <div className="text-sm font-medium" style={{ color: theme.highlight }}>
                {theme.name}
              </div>
              <div className="flex gap-1 mt-2">
                <div className="w-4 h-4 rounded-full" style={{ backgroundColor: theme.primary }} />
                <div className="w-4 h-4 rounded-full" style={{ backgroundColor: theme.highlight }} />
                <div className="w-4 h-4 rounded-full" style={{ backgroundColor: theme.glow }} />
              </div>
            </button>
          ))}
        </div>
      </Card>

      <Card>
        <h2 className="font-heading text-lg font-bold mb-2">About The Abby Project</h2>
        <p className="text-sm text-forge-text-dim">
          Track projects, log hours, earn XP, unlock skills, and get paid
          for your summer maker projects.
        </p>
      </Card>

      <Card>
        <h2 className="font-heading text-lg font-bold mb-4">Account</h2>
        <button
          onClick={onLogout}
          className="flex items-center justify-center gap-2 w-full px-4 py-2.5 rounded-lg border border-forge-border text-forge-text-dim hover:text-red-400 hover:border-red-400/50 transition-colors text-sm"
        >
          <LogOut size={16} /> Log out
        </button>
      </Card>
    </div>
  );
}
