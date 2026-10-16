import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { useRef } from 'react';
import { act, render, screen } from '@testing-library/react';
import useEditorViewport from './useEditorViewport';

let measure;
let disconnected;
function Workspace() {
  const ref = useRef(null);
  const height = useEditorViewport(ref);
  return <section><div ref={ref} data-testid="workspace">{height}</div></section>;
}
beforeEach(() => {
  measure = null; disconnected = vi.fn();
  vi.stubGlobal('ResizeObserver', class {
    constructor(callback) { measure = callback; }
    observe() {}
    disconnect() { disconnected(); }
  });
  vi.spyOn(Element.prototype, 'getBoundingClientRect').mockImplementation(function () {
    if (this.hasAttribute('data-journal-sticky-header')) return { top: 0, bottom: 80, height: 80 };
    if (this.hasAttribute('data-journal-bottom-nav')) return { top: 640, bottom: 700, height: 60 };
    return { top: 160, bottom: 160, height: 0 };
  });
  vi.stubGlobal('innerHeight', 700);
});
afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); });

describe('avatar editor usable viewport', () => {
  it('reserves the actual shell bottom navigation and drains observer/listeners on unmount', () => {
    const view = render(<><div data-journal-sticky-header /><div data-journal-bottom-nav /><Workspace /></>);
    expect(screen.getByTestId('workspace')).toHaveTextContent('468');
    act(() => measure());
    expect(screen.getByTestId('workspace')).toHaveTextContent('468');
    view.unmount();
    expect(disconnected).toHaveBeenCalledOnce();
  });

  it('responds to the visual viewport without reserving offscreen navigation under a keyboard', () => {
    const viewport = new EventTarget();
    Object.assign(viewport, { height: 500, offsetTop: 24 });
    Object.defineProperty(window, 'visualViewport', { configurable: true, value: viewport });
    const view = render(<><div data-journal-bottom-nav /><Workspace /></>);
    expect(screen.getByTestId('workspace')).toHaveTextContent('352');
    viewport.height = 400;
    act(() => viewport.dispatchEvent(new Event('resize')));
    expect(screen.getByTestId('workspace')).toHaveTextContent('252');
    view.unmount();
    delete window.visualViewport;
  });
});
