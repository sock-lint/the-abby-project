import { Fragment, createRef, useImperativeHandle, useRef, useState } from 'react';
import { act, fireEvent, render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import Dropdown from './Dropdown';
import useModalFocus from '../modal/useModalFocus';

const choices = <><option value="">Choose…</option><optgroup label="Activities"><option value="a">Art</option><option value="b" disabled>Blocked</option><option value="c">Cooking</option></optgroup><optgroup label="Unavailable" disabled><option value="d">Dance</option></optgroup><option value="e">Exercise</option></>;

function Controlled({ initial = '', onChange, ...props }) {
  const [value, setValue] = useState(initial);
  return <Dropdown aria-label="Activity" {...props} value={value} onChange={(event) => { onChange?.(event); setValue(event.target.value); }}>{choices}</Dropdown>;
}

function Modal({ onEscape }) {
  const dialogRef = useRef(null);
  useModalFocus({ dialogRef, onEscape });
  return <div ref={dialogRef} role="dialog" tabIndex={-1}><button>Before</button><Controlled /><button>After</button></div>;
}

describe('Dropdown', () => {
  it('opens themed DOM options with selected/disabled groups and real native change events', async () => {
    const user = userEvent.setup();
    const changes = [];
    render(<Controlled onChange={(event) => changes.push({ value: event.target.value, element: event.target.tagName, native: event.nativeEvent.type })} />);
    const trigger = screen.getByRole('combobox', { name: 'Activity' });
    await user.click(trigger);
    expect(trigger).toHaveFocus();
    expect(trigger).toHaveAttribute('aria-expanded', 'true');
    expect(screen.getByRole('option', { name: 'Choose…' })).toHaveAttribute('aria-selected', 'true');
    expect(within(screen.getByRole('group', { name: 'Activities' })).getByRole('option', { name: 'Cooking' })).toBeInTheDocument();
    await user.click(screen.getByRole('option', { name: 'Blocked' }));
    expect(screen.getByRole('listbox')).toBeInTheDocument();
    expect(changes).toEqual([]);
    expect(screen.getByRole('option', { name: 'Dance' })).toHaveAttribute('aria-disabled', 'true');
    await user.click(screen.getByRole('option', { name: 'Cooking' }));
    expect(changes).toEqual([{ value: 'c', element: 'SELECT', native: 'change' }]);
    expect(trigger).toHaveValue('c');
    expect(trigger).toHaveFocus();
    expect(screen.queryByRole('listbox')).not.toBeInTheDocument();
  });

  it('moves virtual focus with arrows/Home/End and commits only on Enter', async () => {
    const user = userEvent.setup();
    render(<Controlled initial="a" />);
    const trigger = screen.getByRole('combobox');
    act(() => trigger.focus());
    await user.keyboard('{ArrowDown}{ArrowDown}');
    expect(trigger).toHaveValue('a');
    expect(screen.getByRole('option', { name: 'Cooking' })).toHaveAttribute('id', trigger.getAttribute('aria-activedescendant'));
    await user.keyboard('{End}');
    expect(screen.getByRole('option', { name: 'Exercise' })).toHaveAttribute('data-active', 'true');
    await user.keyboard('{Home}{ArrowDown}{ArrowDown}{Enter}');
    expect(trigger).toHaveValue('c');
  });

  it('supports typeahead, Escape cancellation and Space selection', async () => {
    const user = userEvent.setup();
    render(<Controlled initial="a" />);
    const trigger = screen.getByRole('combobox');
    act(() => trigger.focus());
    await user.keyboard('co');
    expect(screen.getByRole('option', { name: 'Cooking' })).toHaveAttribute('data-active', 'true');
    await user.keyboard('{Escape}');
    expect(trigger).toHaveValue('a');
    await user.keyboard(' {End} ');
    expect(trigger).toHaveValue('e');
  });

  it('keeps spaces in multiword typeahead until Enter confirms the match', async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(<Dropdown aria-label="Frozen activity" defaultValue="" onChange={onChange}><option value="">-</option><option value="a">Ice cream</option><option value="b">Ice skating</option></Dropdown>);
    const trigger = screen.getByRole('combobox', { name: 'Frozen activity' });
    act(() => trigger.focus());
    await user.keyboard('ice s');
    expect(trigger).toHaveValue('');
    expect(onChange).not.toHaveBeenCalled();
    expect(screen.getByRole('option', { name: 'Ice skating' })).toHaveAttribute('data-active', 'true');
    await user.keyboard('{Enter}');
    expect(trigger).toHaveValue('b');
    expect(onChange).toHaveBeenCalledOnce();
  });

  it('uses Space to confirm a search match after the typeahead buffer expires', () => {
    render(<Dropdown aria-label="Frozen activity" defaultValue=""><option value="">-</option><option value="a">Ice cream</option><option value="b">Ice skating</option></Dropdown>);
    const trigger = screen.getByRole('combobox');
    function keyAt(key, timeStamp) {
      const event = new KeyboardEvent('keydown', { key, bubbles: true, cancelable: true });
      Object.defineProperty(event, 'timeStamp', { value: timeStamp });
      fireEvent(trigger, event);
    }
    keyAt('i', 1000);
    expect(trigger).toHaveValue('');
    keyAt(' ', 1701);
    expect(trigger).toHaveValue('a');
    expect(trigger).toHaveAttribute('aria-expanded', 'false');
  });

  it.each(['{Escape}', '{ArrowDown}', 'click'])('resets phrase typeahead after %s', async (action) => {
    const user = userEvent.setup();
    render(<Dropdown aria-label="Frozen activity" defaultValue=""><option value="">-</option><option value="a">Ice cream</option><option value="b">Ice skating</option></Dropdown>);
    const trigger = screen.getByRole('combobox');
    act(() => trigger.focus());
    await user.keyboard('ice');
    if (action === 'click') {
      await user.click(trigger);
      await user.click(trigger);
    } else await user.keyboard(action);
    // Escape closes; one Space opens and the next confirms. Arrow/click
    // leave a fresh open menu, so Space confirms immediately.
    await user.keyboard(action === '{Escape}' ? '  ' : ' ');
    expect(trigger).toHaveAttribute('aria-expanded', 'false');
    expect(trigger).toHaveValue(action === '{ArrowDown}' ? 'b' : '');
  });

  it('closes on Tab and outside press without stealing destination focus', async () => {
    const user = userEvent.setup();
    render(<><Controlled /><button>Next</button></>);
    const trigger = screen.getByRole('combobox');
    await user.click(trigger);
    await user.tab();
    expect(screen.queryByRole('listbox')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Next' })).toHaveFocus();
    await user.click(trigger);
    await user.click(screen.getByRole('button', { name: 'Next' }));
    expect(trigger).toHaveAttribute('aria-expanded', 'false');
  });

  it('preserves named form submission, default values, native refs and reset', async () => {
    const user = userEvent.setup();
    const ref = createRef();
    const { container } = render(<form><Dropdown ref={ref} aria-label="Activity" name="activity" defaultValue="c">{choices}</Dropdown><button type="reset">Reset</button></form>);
    expect(ref.current.tagName).toBe('SELECT');
    expect(screen.getByRole('combobox')).toHaveValue('c');
    await user.click(screen.getByRole('combobox'));
    await user.click(screen.getByRole('option', { name: 'Art' }));
    expect(new FormData(container.querySelector('form')).get('activity')).toBe('a');
    await user.click(screen.getByRole('button', { name: 'Reset' }));
    expect(screen.getByRole('combobox')).toHaveValue('c');
  });

  it('honors external forms and required validation with a visible linked error', async () => {
    const user = userEvent.setup();
    const submit = vi.fn((event) => event.preventDefault());
    const invalid = vi.fn();
    render(<><form id="task" onSubmit={submit}><button>Save</button></form><Dropdown form="task" name="activity" required aria-label="Activity" onInvalid={invalid}>{choices}</Dropdown></>);
    await user.click(screen.getByRole('button', { name: 'Save' }));
    expect(submit).not.toHaveBeenCalled();
    expect(invalid).toHaveBeenCalledOnce();
    expect(screen.getByRole('combobox')).toHaveFocus();
    expect(screen.getByRole('combobox')).toHaveAttribute('aria-required', 'true');
    expect(screen.getByRole('combobox')).toHaveAttribute('aria-invalid', 'true');
    expect(screen.getByRole('combobox')).toHaveAccessibleDescription(screen.getByRole('alert').textContent);
    await user.click(screen.getByRole('combobox'));
    await user.click(screen.getByRole('option', { name: 'Art' }));
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Save' }));
    expect(submit).toHaveBeenCalledOnce();
  });

  it('handles fragments, numeric values and changing option lists', async () => {
    const user = userEvent.setup();
    const { rerender } = render(<Dropdown aria-label="Number"><Fragment><option value={1}>One</option><option value={2}>Two</option></Fragment></Dropdown>);
    expect(screen.getByRole('combobox')).toHaveValue('1');
    await user.click(screen.getByRole('combobox'));
    await user.click(screen.getByRole('option', { name: 'Two' }));
    expect(screen.getByRole('combobox')).toHaveValue('2');
    rerender(<Dropdown aria-label="Number"><option value={3}>Three</option></Dropdown>);
    expect(screen.getByRole('combobox')).toHaveValue('3');
    expect(screen.getByRole('combobox')).toHaveTextContent('Three');
  });

  it('handles empty lists and disabled fields', async () => {
    const user = userEvent.setup();
    const { rerender } = render(<Dropdown aria-label="Activity" disabled>{choices}</Dropdown>);
    await user.click(screen.getByRole('combobox'));
    expect(screen.queryByRole('listbox')).not.toBeInTheDocument();
    rerender(<Dropdown aria-label="Activity" />);
    await user.click(screen.getByRole('combobox'));
    expect(screen.getByText('No options available')).toBeInTheDocument();
    await user.keyboard('{ArrowDown}{Enter}');
    expect(screen.getByRole('combobox')).toHaveValue('');
  });

  it('supports autofocus on the visible control', () => {
    render(<Dropdown aria-label="Activity" autoFocus>{choices}</Dropdown>);
    expect(screen.getByRole('combobox')).toHaveFocus();
  });

  it('consumes Escape before its modal and keeps normal Tab trapping', async () => {
    const user = userEvent.setup();
    const onEscape = vi.fn();
    render(<Modal onEscape={onEscape} />);
    const trigger = screen.getByRole('combobox');
    await user.click(trigger);
    await user.keyboard('{Escape}');
    expect(trigger).toHaveFocus();
    expect(onEscape).not.toHaveBeenCalled();
    await user.keyboard('{Escape}');
    expect(onEscape).toHaveBeenCalledOnce();
    await user.click(trigger);
    await user.tab();
    expect(screen.queryByRole('listbox')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'After' })).toHaveFocus();
    await user.tab();
    expect(screen.getByRole('button', { name: 'Before' })).toHaveFocus();
  });

  it('keeps virtual focus inside its modal when portaled options are clicked', async () => {
    const user = userEvent.setup();
    render(<Modal onEscape={vi.fn()} />);
    await user.click(screen.getByRole('combobox'));
    await user.click(screen.getByRole('option', { name: 'Exercise' }));
    expect(screen.getByRole('combobox')).toHaveFocus();
    expect(screen.getByRole('combobox')).toHaveValue('e');
  });

  it('keeps the controlled value when a parent declines a change', async () => {
    const user = userEvent.setup();
    render(<Dropdown aria-label="Activity" value="a" onChange={() => {}}>{choices}</Dropdown>);
    await user.click(screen.getByRole('combobox'));
    await user.click(screen.getByRole('option', { name: 'Cooking' }));
    expect(screen.getByRole('combobox')).toHaveValue('a');
  });

  it('forwards blur and focus events from the visible control', async () => {
    const user = userEvent.setup();
    const onFocus = vi.fn();
    const onBlur = vi.fn();
    render(<><Controlled onFocus={onFocus} onBlur={onBlur} /><button>Next</button></>);
    await user.click(screen.getByRole('combobox'));
    await user.tab();
    expect(onFocus).toHaveBeenCalled();
    expect(onBlur).toHaveBeenCalledOnce();
  });
  it('reads options composed by child components and observes their own updates', async () => {
    const user = userEvent.setup();
    const childActions = createRef();
    function ComposedOptions() {
      const [ready, setReady] = useState(false);
      useImperativeHandle(childActions, () => ({ enable: () => setReady(true) }), []);
      return <><option value="first">First</option><optgroup label="Composed"><option value="child" disabled={!ready}>{ready ? 'Child ready' : 'Child waiting'}</option></optgroup></>;
    }
    // The child has its own state; the Dropdown receives the same children
    // element while rendered option labels and disabled attributes change.
    render(<Dropdown aria-label="Composed"><ComposedOptions /></Dropdown>);
    await user.click(screen.getByRole('combobox'));
    expect(within(screen.getByRole('group', { name: 'Composed' })).getByRole('option', { name: 'Child waiting' })).toHaveAttribute('aria-disabled', 'true');
    act(() => childActions.current.enable());
    const child = await screen.findByRole('option', { name: 'Child ready' });
    expect(child).not.toHaveAttribute('aria-disabled');
    await user.click(child);
    expect(screen.getByRole('combobox')).toHaveValue('child');
  });

  it('closes a field when disabled and leaves it closed on reenable', async () => {
    const user = userEvent.setup();
    const { rerender } = render(<Controlled />);
    await user.click(screen.getByRole('combobox'));
    rerender(<Controlled disabled />);
    expect(screen.queryByRole('listbox')).not.toBeInTheDocument();
    rerender(<Controlled />);
    expect(screen.getByRole('combobox')).toHaveAttribute('aria-expanded', 'false');
  });

});
