import { useState } from 'react';
import { createRoot } from 'react-dom/client';
import { MemoryRouter } from 'react-router-dom';
import '../src/index.css';
import Button from '../src/components/Button';
import IconButton from '../src/components/IconButton';
import SectionHeader from '../src/components/SectionHeader';
import { SelectField } from '../src/components/form';
import ConfirmDialog from '../src/components/ConfirmDialog';
import BottomSheet from '../src/components/BottomSheet';
import IncipitBand from '../src/components/atlas/IncipitBand';
import HeaderStatusPips from '../src/components/layout/HeaderStatusPips';
import { PulseContext } from '../src/providers/pulseContext';

function StatusCueFixture() {
  const [coins, setCoins] = useState(1);
  const pulse = { header: { active_timer: null, coin_balance: coins, streak_days: 1 } };
  return (
    <section aria-label="Status cue fixture" className="space-y-2">
      <MemoryRouter>
        <PulseContext.Provider value={{ pulse, refresh: () => {} }}>
          <div className="w-36">
            <HeaderStatusPips user={{ role: 'child' }} />
          </div>
        </PulseContext.Provider>
      </MemoryRouter>
      <Button onClick={() => setCoins(123456789)}>Grow status values</Button>
    </section>
  );
}

export default function Fixture() {
  const [dialog, setDialog] = useState(null);
  return (
    <main className="p-4 max-w-3xl mx-auto space-y-4">
      <IncipitBand letter="C" title="Companions" kicker="Your party" />
      <SectionHeader
        title="Family contribution approvals"
        actions={<><Button variant="secondary">Review history</Button><Button>New contribution</Button></>}
      />
      <SelectField variant="filter" aria-label="Family member">
        <option>AlexandriaWithAnEspeciallyLongFamilyName</option>
        <option>Everyone</option>
      </SelectField>
      <IconButton size="sm" aria-label="Small icon action">×</IconButton>
      <StatusCueFixture />
      <Button onClick={() => setDialog('confirm')}>Open confirmation</Button>
      <Button onClick={() => setDialog('sheet')}>Open sheet</Button>
      {dialog === 'confirm' && (
        <ConfirmDialog
          title="Discard unsaved contribution changes?"
          message={'Review the changes before continuing. '.repeat(35)}
          confirmLabel="Discard contribution changes"
          onCancel={() => setDialog(null)}
          onConfirm={() => setDialog(null)}
        />
      )}
      {dialog === 'sheet' && (
        <BottomSheet title="AlexandriaWithAnEspeciallyLongFamilyName contribution details" onClose={() => setDialog(null)}>
          <p>Contribution details stay readable beside the close control.</p>
        </BottomSheet>
      )}
    </main>
  );
}

createRoot(document.getElementById('root')).render(<Fixture />);
