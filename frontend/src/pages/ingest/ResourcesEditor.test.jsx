import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import ResourcesEditor from './ResourcesEditor.jsx';

describe('ResourcesEditor', () => {
  it('renders resource rows and fires callbacks', async () => {
    const onAdd = vi.fn();
    const user = userEvent.setup();
    render(
      <ResourcesEditor
        resources={[{ url: 'https://x', title: 'X' }]}
        steps={[{ title: 'A' }]}
        onAdd={onAdd}
        onUpdate={vi.fn()}
        onRemove={vi.fn()}
      />,
    );
    expect(screen.getByDisplayValue('https://x')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: /add/i }));
    expect(onAdd).toHaveBeenCalled();
  });
});
