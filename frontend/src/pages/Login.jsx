import { useState, useEffect } from 'react';
import ErrorAlert from '../components/ErrorAlert';
import { getGoogleLoginUrl } from '../api';
import ParchmentCard from '../components/journal/ParchmentCard';
import { buttonPrimary, inputClass } from '../constants/styles';

/**
 * Login — the front page of the journal. Sign-in form on parchment with
 * optional Google OAuth; no book-cover intro gate.
 */
export default function Login({ onLogin }) {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [googleAvailable, setGoogleAvailable] = useState(false);

  useEffect(() => {
    getGoogleLoginUrl()
      .then((data) => {
        if (data?.authorization_url) setGoogleAvailable(true);
      })
      .catch(() => {});

    const params = new URLSearchParams(window.location.search);
    const googleError = params.get('google_error');
    if (googleError === 'no_account') {
      setError('No linked Google account found. Link your Google account in Settings first.');
      window.history.replaceState({}, '', window.location.pathname);
    } else if (googleError === 'inactive') {
      setError('Your account is inactive.');
      window.history.replaceState({}, '', window.location.pathname);
    }
  }, []);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setLoading(true);
    try {
      await onLogin(username, password);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleGoogleLogin = async () => {
    setError('');
    setLoading(true);
    try {
      const data = await getGoogleLoginUrl();
      if (data?.authorization_url) {
        window.location.href = data.authorization_url;
      }
    } catch {
      setError('Could not start Google sign-in.');
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center p-4 parchment-bg">
      <div className="w-full max-w-sm">
        <div className="text-center mb-5">
          <div className="font-script text-sheikah-teal-deep text-base">
            a codex of
          </div>
          <h1 className="font-display italic text-3xl text-ink-primary leading-tight">
            Hyrule Field Notes
          </h1>
        </div>

        <ParchmentCard flourish as="form" onSubmit={handleSubmit}>
          <div className="space-y-4">
            <ErrorAlert message={error} />
            <div>
              <label
                htmlFor="login-username"
                className="block font-script text-sm text-ink-secondary mb-1"
              >
                Name in the ledger
              </label>
              <input
                id="login-username"
                type="text"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                className={inputClass}
                autoFocus
                autoComplete="username"
              />
            </div>
            <div>
              <label
                htmlFor="login-password"
                className="block font-script text-sm text-ink-secondary mb-1"
              >
                Secret word
              </label>
              <input
                id="login-password"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className={inputClass}
                autoComplete="current-password"
              />
            </div>
            <button
              type="submit"
              disabled={loading}
              className={`${buttonPrimary} w-full py-2.5`}
            >
              {loading ? 'Unsealing…' : 'Enter'}
            </button>

            {googleAvailable && (
              <>
                <div className="flex items-center gap-3 font-script text-ink-whisper text-xs">
                  <div className="flex-1 border-t border-ink-page-shadow" />
                  <span>or call upon</span>
                  <div className="flex-1 border-t border-ink-page-shadow" />
                </div>
                <button
                  type="button"
                  onClick={handleGoogleLogin}
                  disabled={loading}
                  className="w-full flex items-center justify-center gap-2 bg-ink-page border border-ink-page-shadow text-ink-primary font-body py-2.5 rounded-lg hover:bg-ink-page-rune-glow transition-colors disabled:opacity-50"
                >
                  {/* intentional: official Google brand colors required for the Sign-in-with-Google logo (#4285F4 / #34A853 / #FBBC05 / #EA4335) */}
                  <svg viewBox="0 0 24 24" width="18" height="18">
                    <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92a5.06 5.06 0 0 1-2.2 3.32v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.1z" />
                    <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" />
                    <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" />
                    <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" />
                  </svg>
                  Sign in with Google
                </button>
              </>
            )}
          </div>
        </ParchmentCard>
      </div>
    </div>
  );
}
