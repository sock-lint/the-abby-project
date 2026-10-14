import { it, expect, vi, beforeEach } from 'vitest';
import { useState } from 'react';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import AttachmentField from './AttachmentField';

beforeEach(() => {
  URL.createObjectURL = vi.fn((file) => `blob:${file.name}`);
  URL.revokeObjectURL = vi.fn();
});
function PhotoField({ disabled = false, error }) {
  const [file, setFile] = useState(null);
  return <AttachmentField label="Photo" file={file} onChange={setFile} accept="image/*"
    previewImage disabled={disabled} helpText="Image files." error={error} />;
}
it('replaces, removes and reselects the same image while releasing local preview URLs', async () => {
  const user = userEvent.setup();
  const view = render(<PhotoField />);
  const input = screen.getByLabelText('Photo', { selector: 'input' });
  const first = new File(['first'], 'first.png', { type: 'image/png' });
  await user.upload(input, first);
  expect(await screen.findByRole('img', { name: 'Photo preview' })).toHaveAttribute('src', 'blob:first.png');
  expect(screen.getByText('5 bytes')).toBeInTheDocument();
  await user.upload(input, new File(['replacement'], 'second.png', { type: 'image/png' }));
  await waitFor(() => expect(screen.getByRole('img')).toHaveAttribute('src', 'blob:second.png'));
  expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:first.png');
  await user.click(screen.getByRole('button', { name: 'Remove photo' }));
  expect(screen.queryByRole('img')).toBeNull();
  expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:second.png');
  await user.upload(input, first);
  await screen.findByRole('img');
  view.unmount();
  expect(URL.revokeObjectURL).toHaveBeenCalledTimes(3);
});
it('connects domain validation errors and format guidance to the chooser while retaining the selected file', async () => {
  const user = userEvent.setup();
  const view = render(<PhotoField />);
  const input = screen.getByLabelText('Photo', { selector: 'input' });
  expect(input).toHaveAttribute('accept', 'image/*');
  await user.upload(input, new File(['pixels'], 'memory.png', { type: 'image/png' }));
  view.rerender(<PhotoField error="This image could not be read." />);
  expect(screen.getByText('memory.png')).toBeInTheDocument();
  expect(input).toHaveAttribute('aria-invalid', 'true');
  expect(screen.getByRole('button', { name: 'Replace photo' })).toHaveAccessibleDescription('Image files. This image could not be read.');
  expect(screen.getByRole('alert')).toHaveTextContent('This image could not be read.');
});
it('keeps the file controls disabled during the owning form upload', async () => {
  const changed = vi.fn();
  render(<AttachmentField label="Model file" file={new File(['model'], 'dragon.stl')} onChange={changed} disabled />);
  expect(screen.getByRole('button', { name: 'Replace model file' })).toBeDisabled();
  expect(screen.getByRole('button', { name: 'Remove model file' })).toBeDisabled();
  await userEvent.setup().click(screen.getByRole('button', { name: 'Remove model file' }));
  expect(changed).not.toHaveBeenCalled();
});
it('keeps filename information if an image preview cannot decode', async () => {
  const user = userEvent.setup();
  render(<PhotoField />);
  await user.upload(screen.getByLabelText('Photo', { selector: 'input' }), new File(['pixels'], 'memory.png', { type: 'image/png' }));
  fireEvent.error(await screen.findByRole('img'));
  expect(screen.getByText(/Preview unavailable/)).toBeInTheDocument();
  expect(screen.getByText('memory.png')).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Replace photo' })).toBeEnabled();
});
