import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import SourceStep from './SourceStep.jsx';

describe('SourceStep', () => {
  it.each(['url', 'pdf'])('discloses the AI transfer before starting a %s import', async (sourceTab) => {
    const onStart = vi.fn();
    const user = userEvent.setup();
    render(
      <SourceStep
        sourceTab={sourceTab} setSourceTab={vi.fn()}
        url="https://example.com/how-to" setUrl={vi.fn()}
        file={new File(['tutorial'], 'tutorial.pdf', { type: 'application/pdf' })} setFile={vi.fn()}
        onStart={onStart}
      />,
    );

    const disclosure = screen.getByText(/up to 12,000 characters of extracted text/i);
    expect(disclosure).toBeVisible();
    expect(disclosure).toHaveTextContent('Anthropic (Claude)');
    expect(disclosure).toHaveTextContent('source title');
    expect(disclosure).toHaveTextContent('If AI import is enabled');
    expect(disclosure).toHaveTextContent('Processing starts before review');
    expect(screen.getByRole('link', { name: 'Privacy details' })).toHaveAttribute('href', '/privacy/#ai');
    expect(onStart).not.toHaveBeenCalled();

    await user.click(screen.getByRole('button', { name: 'Parse Source' }));
    expect(onStart).toHaveBeenCalledTimes(1);
  });

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

  it('labels the PDF picker and sends the selected file to the form', async () => {
    const setFile = vi.fn();
    const user = userEvent.setup();
    const file = new File(['tutorial'], 'Bird feeder tutorial.pdf', { type: 'application/pdf' });
    render(
      <SourceStep
        sourceTab="pdf" setSourceTab={vi.fn()}
        url="" setUrl={vi.fn()} file={null} setFile={setFile}
        onStart={vi.fn()}
      />,
    );
    await user.upload(screen.getByLabelText('PDF Tutorial'), file);
    expect(setFile).toHaveBeenCalledWith(file);
  });
});
