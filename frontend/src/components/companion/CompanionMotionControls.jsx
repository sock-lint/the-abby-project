import { useState } from 'react';
import Button from '../Button';
import { SelectField } from '../form';

export default function CompanionMotionControls({ motions, disabled, onPlay }) {
  const [selected, setSelected] = useState(motions.find((motion) => motion.motion === 'idle' || motion.id === 'idle')?.id
    || motions.find((motion) => motion.action === 'idle')?.id || motions[0].id);
  const motion = motions.find((entry) => entry.id === selected) || motions[0];
  return <details className="companion-motion-library">
    <summary>More motions</summary>
    <div className="companion-motion-picker">
      <SelectField label="Companion motion" value={selected} onChange={(event) => setSelected(event.target.value)}
        helpText={motion.loop ? 'Repeats until you choose another motion or return to rest.' : 'Plays once, then returns to rest.'}>
        {motions.map((entry) => <option key={entry.id} value={entry.id}>{entry.label}</option>)}
      </SelectField>
      <div className="companion-play-controls">
        <Button size="sm" variant="secondary" disabled={disabled} onClick={() => onPlay(motion)}>Play motion</Button>
        <Button size="sm" variant="ghost" disabled={disabled} onClick={() => onPlay({ id: 'idle', label: 'Rest' })}>Return to rest</Button>
      </div>
    </div>
  </details>;
}
