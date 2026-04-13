import { useState, useEffect } from 'react';
import { Hammer } from 'lucide-react';
import ErrorAlert from '../components/ErrorAlert';
import { getGoogleLoginUrl } from '../api';

export default function Login({ onLogin }) {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [googleAvailable, setGoogleAvailable] = useState(false);

  useEffect(() => {
    // Check if Google OAuth is configured on the backend
    getGoogleLoginUrl()
      .then((data) => { if (data?.authorization_url) setGoogleAvailable(true); })
      .catch(() => {});

    // Show error if redirected back from failed Google login
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
    <div className="min-h-screen flex items-center justify-center bg-forge-bg p-4">
      <div className="w-full max-w-sm">
        <div className="text-center mb-8">
          <div className="w-16 h-16 bg-amber-primary/20 rounded-2xl flex items-center justify-center mx-auto mb-4">
            <Hammer className="text-amber-highlight" size={32} />
          </div>
          <h1 className="font-heading text-2xl text-amber-highlight font-bold">The Abby Project</h1>
          <p className="text-forge-text-dim text-sm mt-1">Projects, chores, homework — earn and learn</p>
        </div>
        <form onSubmit={handleSubmit} className="bg-forge-card border border-forge-border rounded-xl p-6 space-y-4">
          <ErrorAlert message={error} />
          <div>
            <label className="block text-sm text-forge-text-dim mb-1">Username</label>
            <input
              type="text"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              className="w-full bg-forge-bg border border-forge-border rounded-lg px-3 py-2 text-forge-text focus:outline-none focus:border-amber-primary"
              autoFocus
            />
          </div>
          <div>
            <label className="block text-sm text-forge-text-dim mb-1">Password</label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full bg-forge-bg border border-forge-border rounded-lg px-3 py-2 text-forge-text focus:outline-none focus:border-amber-primary"
            />
          </div>
          <button
            type="submit"
            disabled={loading}
            className="w-full bg-amber-primary hover:bg-amber-highlight text-black font-semibold py-2.5 rounded-lg transition-colors disabled:opacity-50"
          >
            {loading ? 'Signing in...' : 'Sign In'}
          </button>

          {googleAvailable && (
            <>
              <div className="flex items-center gap-3 text-forge-text-dim text-xs">
                <div className="flex-1 border-t border-forge-border" />
                <span>or</span>
                <div className="flex-1 border-t border-forge-border" />
              </div>
              <button
                type="button"
                onClick={handleGoogleLogin}
                disabled={loading}
                className="w-full flex items-center justify-center gap-2 bg-white hover:bg-gray-50 text-gray-700 font-medium py-2.5 rounded-lg border border-gray-300 transition-colors disabled:opacity-50"
              >
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
        </form>
      </div>
    </div>
  );
}
