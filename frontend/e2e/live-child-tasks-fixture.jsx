import { createRoot } from 'react-dom/client';
import { BrowserRouter, Route, Routes } from 'react-router-dom';
import { MotionConfig } from 'framer-motion';
import { AuthProvider } from '../src/hooks/useApi';
import { STORAGE_KEYS } from '../src/constants/storage';
import QuestsHub from '../src/pages/quests';
import Portfolio from '../src/pages/Portfolio';
import TreasuryHub from '../src/pages/treasury';
import '../src/index.css';

// This credential exists only on the disposable loopback fixture origin.
localStorage.setItem(STORAGE_KEYS.AUTH_TOKEN, 'offline-child-tasks-synthetic-token');

createRoot(document.getElementById('root')).render(
  <BrowserRouter><AuthProvider><MotionConfig reducedMotion="user">
    <main><Routes>
      <Route path="/quests" element={<QuestsHub />} />
      <Route path="/treasury" element={<TreasuryHub />} />
      <Route path="/chronicle" element={<Portfolio />} />
    </Routes></main>
  </MotionConfig></AuthProvider></BrowserRouter>,
);
