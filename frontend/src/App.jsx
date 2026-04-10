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
import ClockPage from './pages/ClockPage';
import Timecards from './pages/Timecards';
import Payments from './pages/Payments';
import Rewards from './pages/Rewards';
import Achievements from './pages/Achievements';
import Portfolio from './pages/Portfolio';
import SettingsPage from './pages/SettingsPage';
import Loader from './components/Loader';

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
    <BrowserRouter>
      <Routes>
        <Route element={<Layout user={user} onLogout={logout} />}>
          <Route path="/" element={<Dashboard />} />
          <Route path="/projects" element={<Projects user={user} />} />
          <Route path="/projects/new" element={<ProjectNew />} />
          <Route path="/projects/ingest" element={<ProjectIngest />} />
          <Route path="/projects/:id" element={<ProjectDetail user={user} />} />
          <Route path="/clock" element={<ClockPage />} />
          <Route path="/timecards" element={<Timecards user={user} />} />
          <Route path="/payments" element={<Payments />} />
          <Route path="/rewards" element={<Rewards />} />
          <Route path="/achievements" element={<Achievements />} />
          <Route path="/portfolio" element={<Portfolio />} />
          <Route path="/settings" element={<SettingsPage user={user} onLogout={logout} />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
