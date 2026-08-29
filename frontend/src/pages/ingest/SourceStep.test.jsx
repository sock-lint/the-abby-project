import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import SourceStep from './SourceStep.jsx';

describe('SourceStep', () => {
  it('renders URL tab by default', () => {
    render(
      <SourceStep
        sourceTab="url" setSourceTab={vi.fn()}
        url="" setUrl={vi.fn()}
        file={null} setFile={vi.fn()}
        onStart={vi.fn()}
      />,
    );
    expect(screen.getAllByRole('button').length).toBeGreaterThan(0);
  });

  it('switches to PDF tab', async () => {
    const setSourceTab = vi.fn();
    const user = userEvent.setup();
    render(
      <SourceStep
        sourceTab="url" setSourceTab={setSourceTab}
        url="" setUrl={vi.fn()} file={null} setFile={vi.fn()}
        onStart={vi.fn()}
      />,
    );
    await user.click(screen.getByRole('button', { name: /pdf/i }));
    expect(setSourceTab).toHaveBeenCalledWith('pdf');
  });

  it('disables and relabels the start button while a job is being opened', () => {
    render(
      <SourceStep
        sourceTab="url" setSourceTab={vi.fn()}
        url="https://example.com/how-to" setUrl={vi.fn()}
        file={null} setFile={vi.fn()}
        onStart={vi.fn()}
        starting
      />,
    );
    const start = screen.getByRole('button', { name: /reading/i });
    expect(start).toBeDisabled();
    expect(screen.queryByRole('button', { name: /parse source/i })).toBeNull();
  });

  it('types into the URL input', async () => {
    const setUrl = vi.fn();
    const user = userEvent.setup();
    render(
      <SourceStep
        sourceTab="url" setSourceTab={vi.fn()}
        url="" setUrl={setUrl} file={null} setFile={vi.fn()}
        onStart={vi.fn()}
      />,
    );
    await user.type(document.querySelector('input[type="url"]'), 'h');
    expect(setUrl).toHaveBeenCalled();
  });
});
