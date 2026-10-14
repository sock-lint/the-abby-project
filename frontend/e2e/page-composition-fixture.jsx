import { createRoot } from 'react-dom/client';
import { MemoryRouter } from 'react-router-dom';
import '../src/index.css';
import { AuthProvider, useAuth } from '../src/hooks/useApi';
import Achievements from '../src/pages/Achievements';
import Inventory from '../src/pages/Inventory';
import Rewards from '../src/pages/Rewards';
import Portfolio from '../src/pages/Portfolio';
import Yearbook from '../src/pages/Yearbook';
import SettingsPage from '../src/pages/SettingsPage';
import Manage from '../src/pages/Manage';
import ClockPage from '../src/pages/ClockPage';
import Payments from '../src/pages/Payments';
import Timecards from '../src/pages/Timecards';

const params = new URLSearchParams(window.location.search);
const pages = { skills: Achievements, inventory: Inventory, rewards: Rewards, portfolio: Portfolio,
  yearbook: Yearbook, settings: SettingsPage, manage: Manage, clock: ClockPage, payments: Payments, timecards: Timecards };
const Page = pages[params.get('page')] || Achievements;
// The local Playwright runner intercepts every API call with synthetic data.
localStorage.setItem('abby_auth_token', 'synthetic-page-composition-token');

export default function Fixture() {
  const { loading } = useAuth();
  return <main className="p-4">{loading ? <p>Loading fixture</p> : <Page />}</main>;
}

createRoot(document.getElementById('root')).render(<MemoryRouter initialEntries={[window.location.pathname + window.location.search]}>
  <AuthProvider><Fixture /></AuthProvider>
</MemoryRouter>);
