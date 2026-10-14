import { useEffect, useState } from 'react';
import { MotionConfig, useReducedMotion } from 'framer-motion';
import { SelectField, CheckboxField } from '../../components/form';
import ParchmentCard from '../../components/journal/ParchmentCard';
import TabList from '../../components/layout/TabList';
import { applyTheme, themes } from '../../themes';
import { DesignPreviewContext } from './preview.context';

const navigation = ['Today', 'Tasks', 'Pets', 'Rewards', 'Progress', 'Memories'].map(label => ({ id: label, label }));

export default function DesignEnvironment({ children }) {
  const [theme, setTheme] = useState(() => {
    const value = new URLSearchParams(window.location.search).get('theme');
    return Object.hasOwn(themes, value) ? value : 'hyrule';
  });
  const [width, setWidth] = useState('responsive');
  const [role, setRole] = useState('child');
  const [longContent, setLongContent] = useState(false);
  const [largeText, setLargeText] = useState(false);
  const [reducedMotion, setReducedMotion] = useState(false);
  const [chrome, setChrome] = useState(false);
  const [activeChapter, setActiveChapter] = useState('Today');
  const deviceReducedMotion = useReducedMotion();

  useEffect(() => { applyTheme(theme); }, [theme]);
  useEffect(() => {
    if (reducedMotion) document.body.dataset.designReducedMotion = 'true';
    else delete document.body.dataset.designReducedMotion;
    return () => { delete document.body.dataset.designReducedMotion; };
  }, [reducedMotion]);

  return (
    <MotionConfig reducedMotion={reducedMotion || deviceReducedMotion ? 'always' : 'user'}>
      <style>{'[data-design-reduced-motion="true"] *, [data-design-reduced-motion="true"] *::before, [data-design-reduced-motion="true"] *::after { animation: none !important; transition-duration: 0s !important; }'}</style>
      <div className="max-w-6xl mx-auto px-4 py-4 space-y-4">
        <ParchmentCard as="aside" aria-label="Design preview settings" className="space-y-3">
          <p className="font-body text-body text-ink-secondary">
            Local, synthetic examples. Preview settings change this page only; examples never save account data or grant rewards.
          </p>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            <SelectField label="Color theme" value={theme} onChange={event => setTheme(event.target.value)}>
              {Object.entries(themes).map(([key, cover]) => <option key={key} value={key}>{cover.name}</option>)}
            </SelectField>
            <SelectField label="Preview width" value={width} onChange={event => setWidth(event.target.value)}>
              <option value="responsive">Available width</option>
              <option value="320">Small phone · 320px</option>
              <option value="375">Phone · 375px</option>
              <option value="768">Tablet · 768px</option>
              <option value="1280">Desktop · 1280px</option>
            </SelectField>
            <SelectField label="Example role" value={role} onChange={event => setRole(event.target.value)}>
              <option value="child">Child</option>
              <option value="parent">Parent</option>
            </SelectField>
          </div>
          <div className="flex flex-wrap gap-x-5 gap-y-2">
            <CheckboxField label="Long content" checked={longContent} onChange={event => setLongContent(event.target.checked)} />
            <CheckboxField label="Larger text" checked={largeText} onChange={event => setLargeText(event.target.checked)} />
            <CheckboxField label="Preview reduced motion" checked={reducedMotion} onChange={event => setReducedMotion(event.target.checked)} />
            <CheckboxField label="Show navigation example" checked={chrome} onChange={event => setChrome(event.target.checked)} />
          </div>
          <p className="text-caption text-ink-secondary">Device motion preference: {deviceReducedMotion ? 'reduced' : 'standard'}. Use browser zoom and device settings to check the full accessibility behavior.</p>
          <nav aria-label="Design sections" className="flex flex-wrap gap-2">
            {[
              ['design-foundations', 'Foundations'], ['design-data', 'Data and feedback'],
              ['design-forms', 'Forms and dialogs'], ['design-recipes', 'Page recipes'],
              ['design-outcomes', 'Status and outcomes'],
            ].map(([id, label]) => <a key={id} href={`#${id}`} className="inline-flex min-h-11 items-center px-3 rounded-lg underline text-body text-sheikah-teal-deep">{label}</a>)}
          </nav>
        </ParchmentCard>
        <div
          data-design-canvas="true"
          className="mx-auto min-w-0 w-full"
          style={{
            maxWidth: width === 'responsive' ? undefined : `${width}px`,
            ...(largeText ? { '--text-body': '20px', '--text-caption': '17px', '--text-tiny': '16px', '--text-micro': '15px', '--text-base': '22px', '--text-sm': '19px' } : {}),
          }}
        >
          {chrome && <TabList tabs={navigation} activeId={activeChapter} onSelect={setActiveChapter} ariaLabel="Preview navigation" />}
          <DesignPreviewContext.Provider value={{ role, longContent }}>{children}</DesignPreviewContext.Provider>
        </div>
      </div>
    </MotionConfig>
  );
}
