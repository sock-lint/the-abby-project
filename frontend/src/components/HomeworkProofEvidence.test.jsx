import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import HomeworkProofEvidence from './HomeworkProofEvidence';

describe('HomeworkProofEvidence', () => {
  it.each(['https://drive.google.com/file/d/synthetic-proof/view', 'http://example.test/completed-work'])('opens a safe proof URL as an external link: %s', (proofUrl) => {
    const { container } = render(<HomeworkProofEvidence proofUrl={proofUrl} />);
    const link = screen.getByRole('link', { name: /open proof link/i });
    expect(link).toHaveAttribute('href', proofUrl);
    expect(link).toHaveAttribute('target', '_blank');
    expect(link).toHaveAttribute('rel', 'noopener noreferrer');
    expect(link).toHaveAccessibleName(/opens in a new tab/i);
    expect(container.querySelector('iframe, embed, object, img')).toBeNull();
  });

  it.each(['javascript:alert(1)', 'data:text/html,proof', 'file:///tmp/proof', '//example.test/proof', '/proof', 'https://user:password@example.test/proof', 'not a URL', '', null, 42])('does not render an unsafe or missing saved proof URL: %s', (proofUrl) => {
    const { container } = render(<HomeworkProofEvidence proofUrl={proofUrl} />);
    expect(screen.queryByRole('link')).not.toBeInTheDocument();
    expect(container).toBeEmptyDOMElement();
  });

  it('keeps proof photos browsable alongside a link', async () => {
    const user = userEvent.setup();
    render(<HomeworkProofEvidence
      proofs={[{ id: 1, image: 'https://example.test/completed-page.jpg', caption: 'Completed page' }]}
      proofUrl="https://docs.google.com/document/d/synthetic-proof/edit"
    />);
    await user.click(screen.getByRole('button', { name: 'View Completed page' }));
    expect(await screen.findByRole('dialog', { name: 'Photo viewer' })).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Close photo viewer' }));
    expect(screen.getByRole('link', { name: /open proof link/i })).toBeInTheDocument();
  });

  it('preserves photos when a legacy proof URL is unsafe', () => {
    render(<HomeworkProofEvidence
      proofs={[{ id: 1, image: 'https://example.test/completed-page.jpg', caption: 'Completed page' }]}
      proofUrl="javascript:alert(1)"
    />);
    expect(screen.getByRole('button', { name: 'View Completed page' })).toBeInTheDocument();
    expect(screen.queryByRole('link')).not.toBeInTheDocument();
  });
});
