import { useState } from 'react';
import { createRoot } from 'react-dom/client';
import '../src/index.css';
import { applyTheme } from '../src/themes';
import Button from '../src/components/Button';
import HomeworkSubmitSheet from '../src/components/HomeworkSubmitSheet';
import HomeworkProofEvidence from '../src/components/HomeworkProofEvidence';

const assignment = {
  id: 42,
  title: 'Share the completed science report with a parent',
  description: 'Finish the experiment report.\nInclude your observations and conclusion.',
  subject: 'science',
  timeliness_preview: { timeliness: 'on_time' },
};
const proofUrl = `https://drive.google.com/file/d/synthetic-homework-proof/view?usp=sharing&resourcekey=${'a'.repeat(900)}#page=2`;
applyTheme(new URLSearchParams(window.location.search).get('theme'));

export default function Fixture() {
  const [open, setOpen] = useState(false);
  const [submitted, setSubmitted] = useState(false);
  return (
    <main className="max-w-3xl mx-auto p-4 space-y-4">
      <h1 className="font-display text-lede text-ink-primary">Homework proof</h1>
      <section aria-label="Parent proof review" className="rounded-xl bg-ink-page-aged p-4">
        <HomeworkProofEvidence proofUrl={proofUrl} />
      </section>
      <Button onClick={() => setOpen(true)}>Submit homework proof</Button>
      {submitted && <p role="status">Homework submitted for review.</p>}
      {open && <HomeworkSubmitSheet
        assignment={assignment}
        onClose={() => setOpen(false)}
        onSubmitted={() => { setOpen(false); setSubmitted(true); }}
      />}
    </main>
  );
}

createRoot(document.getElementById('root')).render(<Fixture />);
