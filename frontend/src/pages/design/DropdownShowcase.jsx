import { useState } from 'react';
import { SelectField } from '../../components/form';
import BottomSheet from '../../components/BottomSheet';
import Button from '../../components/Button';
import ParchmentCard from '../../components/journal/ParchmentCard';

export default function DropdownShowcase() {
  const [subject, setSubject] = useState('math');
  const [filter, setFilter] = useState('all');
  const [activity, setActivity] = useState('drawing');
  const [child, setChild] = useState('');
  const [open, setOpen] = useState(false);
  const [selection, setSelection] = useState('');

  return (
    <section id="design-dropdowns" aria-labelledby="dropdowns-heading" className="space-y-4 scroll-mt-4">
      <h2 id="dropdowns-heading" className="font-display text-2xl font-bold text-ink-primary">Dropdowns</h2>
      <p className="text-body text-ink-secondary max-w-prose">
        Shared dropdowns use your color theme for both the field and the open menu.
        Choose with a tap, arrow keys or by typing the start of an option.
        Escape cancels a choice; Tab continues through the form.
      </p>
      <ParchmentCard className="space-y-4">
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <SelectField label="Homework subject" value={subject} onChange={event => setSubject(event.target.value)}>
            <option value="math">Math</option>
            <option value="reading">Reading</option>
            <option value="science">Science</option>
            <option value="art">Art</option>
          </SelectField>
          <SelectField label="Activity filter" variant="filter" value={filter} onChange={event => setFilter(event.target.value)}>
            <option value="all">All activities</option>
            <option value="active">In progress</option>
            <option value="done">Completed</option>
          </SelectField>
        </div>
        <SelectField
          label="Grouped activities" value={activity} onChange={event => setActivity(event.target.value)}
          helpText="Long choices wrap. Unavailable choices remain readable and cannot be selected."
        >
          <optgroup label="Creative">
            <option value="drawing">Drawing</option>
            <option value="long">A very long activity name that wraps onto another line on a small phone</option>
          </optgroup>
          <optgroup label="Movement">
            <option value="walking">Walking</option>
            <option value="swimming" disabled>Swimming — unavailable</option>
          </optgroup>
        </SelectField>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <SelectField label="Unavailable dropdown" disabled value="loading" helpText="Disabled while choices are loading.">
            <option value="loading">Loading choices…</option>
          </SelectField>
          <SelectField label="Dropdown with an error" defaultValue="" error="Choose an activity before continuing.">
            <option value="">Choose an activity…</option>
            <option value="drawing">Drawing</option>
          </SelectField>
        </div>
        <Button variant="secondary" onClick={() => setOpen(true)}>Preview dropdown in a form</Button>
        <p role="status" aria-label="Dropdown preview selection" className="text-body text-ink-secondary">
          {selection || 'Selections in this preview stay on this page.'}
        </p>
        <pre className="overflow-x-auto rounded-lg bg-ink-page p-3 text-caption text-ink-secondary"><code>{'import { SelectField } from "../components/form";\n\n<SelectField label="Subject" value={subject}\n  onChange={event => setSubject(event.target.value)}>\n  <option value="math">Math</option>\n</SelectField>'}</code></pre>
        <p className="text-caption text-ink-secondary">
          Used by Homework assignments, child selectors, project filters, skill tags and Settings.
        </p>
      </ParchmentCard>
      {open && (
        <BottomSheet title="Dropdown form preview" onClose={() => setOpen(false)}>
          <form className="space-y-4" onSubmit={event => {
            event.preventDefault();
            setSelection(`Selected child: ${child}. No account data was saved.`);
            setOpen(false);
          }}>
            <p className="text-body text-ink-secondary">The menu stays visible inside a scrolling form, including short phone screens.</p>
            <SelectField label="Assignment child" required value={child} onChange={event => setChild(event.target.value)}>
              <option value="">Choose a child…</option>
              {['Alex', 'Casey', 'Drew', 'Elliot', 'Frankie', 'Harper', 'Jamie', 'Jordan', 'Morgan', 'Riley', 'Sam', 'Taylor'].map(name => (
                <option key={name} value={name}>{name}</option>
              ))}
            </SelectField>
            <div className="flex flex-wrap gap-3">
              <Button type="submit">Use selection</Button>
              <Button variant="secondary" onClick={() => setOpen(false)}>Cancel</Button>
            </div>
          </form>
        </BottomSheet>
      )}
    </section>
  );
}
