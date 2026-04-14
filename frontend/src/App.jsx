import * as Sentry from '@sentry/react';
import { useEffect } from 'react';
import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { useAuth } from './hooks/useApi';
import { applyTheme } from './themes';
import Layout from './components/Layout';
import Login from './pages/Login';
import Dashboard from './pages/Dashboard';
import Projects from './pages/Projects';
import ProjectDetail from './pages/ProjectDetail';
import ProjectNew from './pages/ProjectNew';
import ProjectIngest from './pages/ProjectIngest';
import Chores from './pages/Chores';
import Homework from './pages/Homework';
import Habits from './pages/Habits';
import Inventory from './pages/Inventory';
import Stable from './pages/Stable';
import Quests from './pages/Quests';
import ClockPage from './pages/ClockPage';
import Timecards from './pages/Timecards';
import Payments from './pages/Payments';
import Rewards from './pages/Rewards';
import Achievements from './pages/Achievements';
import Portfolio from './pages/Portfolio';
import Manage from './pages/Manage';
import SettingsPage from './pages/SettingsPage';
import Loader from './components/Loader';

function ErrorFallback({ error, resetError }) {
  return (
    <div className="min-h-screen flex flex-col items-center justify-center bg-forge-bg p-8 gap-4">
      <h1 className="text-xl font-bold text-red-400">Something went wrong</h1>
      <p className="text-forge-muted text-sm">{error?.message}</p>
      <button
        onClick={resetError}
        className="px-4 py-2 bg-forge-accent text-white rounded-lg"
      >
        Try again
      </button>
    </div>
  );
}

export default function App() {
  const { user, loading, login, logout } = useAuth();

  useEffect(() => {
    if (user?.theme) applyTheme(user.theme);
  }, [user?.theme]);

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-forge-bg">
        <Loader />
      </div>
    );
  }

  if (!user) {
    return <Login onLogin={login} />;
  }

  return (
    <Sentry.ErrorBoundary fallback={ErrorFallback} showDialog={false}>
      <BrowserRouter>
        <Routes>
          <Route element={<Layout user={user} onLogout={logout} />}>
            <Route path="/" element={<Dashboard />} />
            <Route path="/projects" element={<Projects user={user} />} />
            <Route path="/projects/new" element={<ProjectNew />} />
            <Route path="/projects/ingest" element={<ProjectIngest />} />
            <Route path="/projects/:id" element={<ProjectDetail user={user} />} />
            <Route path="/chores" element={<Chores />} />
            <Route path="/homework" element={<Homework />} />
            <Route path="/habits" element={<Habits />} />
            <Route path="/inventory" element={<Inventory />} />
            <Route path="/stable" element={<Stable />} />
            <Route path="/quests" element={<Quests />} />
            <Route path="/clock" element={<ClockPage />} />
            <Route path="/timecards" element={<Timecards user={user} />} />
            <Route path="/payments" element={<Payments />} />
            <Route path="/rewards" element={<Rewards />} />
            <Route path="/achievements" element={<Achievements />} />
            <Route path="/portfolio" element={<Portfolio />} />
            <Route path="/manage" element={<Manage />} />
            <Route path="/settings" element={<SettingsPage user={user} onLogout={logout} />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </Sentry.ErrorBoundary>
  );
}
