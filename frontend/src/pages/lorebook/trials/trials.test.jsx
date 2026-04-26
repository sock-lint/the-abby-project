import { describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import TapAndRewardTrial from './TapAndRewardTrial.jsx';
import ScribeTrial from './ScribeTrial.jsx';
import ObserveTrial from './ObserveTrial.jsx';
import ChoiceTrial from './ChoiceTrial.jsx';
import DragToTargetTrial from './DragToTargetTrial.jsx';
import SequenceTrial from './SequenceTrial.jsx';

vi.mock('framer-motion', async () => {
  const a = await vi.importActual('framer-motion');
  return {
    ...a,
    AnimatePresence: ({ children }) => children,
    motion: {
      ...a.motion,
      li: ({ children, ...props }) => <li {...props}>{children}</li>,
      div: ({ children, ...props }) => <div {...props}>{children}</div>,
      button: ({ children, ...props }) => <button {...props}>{children}</button>,
    },
  };
});

const tapEntry = {
  slug: 'duties',
  title: 'Duties',
  trial: {
    prompt: 'Tap the dish.',
    payoff: '+1 coin',
    target_icon: '🍽️',
    reward_icon: '🪙',
  },
};

describe('TapAndRewardTrial', () => {
  it('fires onReady when the target is tapped', async () => {
    const onReady = vi.fn();
    const user = userEvent.setup();
    render(<TapAndRewardTrial entry={tapEntry} onReady={onReady} />);

    await user.click(screen.getByRole('button', { name: /tap the dish/i }));
    expect(onReady).toHaveBeenCalledTimes(1);
    expect(screen.getByText('+1 coin')).toBeInTheDocument();
  });

  it('also fires onReady from the "I get it" affordance', async () => {
    const onReady = vi.fn();
    const user = userEvent.setup();
    render(<TapAndRewardTrial entry={tapEntry} onReady={onReady} />);

    await user.click(screen.getByRole('button', { name: /i get it/i }));
    expect(onReady).toHaveBeenCalled();
  });
});

describe('ScribeTrial', () => {
  it('disables commit until min_length is reached, fires onReady on commit', async () => {
    const entry = {
      trial: {
        prompt: 'Inscribe what mattered.',
        payoff: '+15 XP',
        min_length: 4,
        placeholder: 'Today I…',
      },
    };
    const onReady = vi.fn();
    const user = userEvent.setup();
    render(<ScribeTrial entry={entry} onReady={onReady} />);

    const textarea = screen.getByPlaceholderText(/today i/i);
    const commit = screen.getByRole('button', { name: /commit to the page/i });
    expect(commit).toBeDisabled();

    await user.type(textarea, 'wow');
    expect(commit).toBeDisabled();
    await user.type(textarea, 'a');
    expect(commit).toBeEnabled();

    await user.click(commit);
    expect(onReady).toHaveBeenCalledTimes(1);
    expect(screen.getByText('+15 XP')).toBeInTheDocument();
  });
});

describe('ObserveTrial', () => {
  it('reaches the witnessed state and fires onReady eventually', async () => {
    const entry = { trial: { prompt: 'Watch.', payoff: 'A page is added' } };
    const onReady = vi.fn();
    render(<ObserveTrial entry={entry} onReady={onReady} />);

    expect(screen.getByText(/observing/i)).toBeInTheDocument();
    await waitFor(() => expect(onReady).toHaveBeenCalled(), { timeout: 5000 });
    expect(screen.getByText(/a page is added/i)).toBeInTheDocument();
  }, 8000);
});

describe('ChoiceTrial', () => {
  it('fires onReady when a choice is picked and disables siblings', async () => {
    const entry = {
      trial: {
        prompt: 'Pick one.',
        payoff: 'Quest begins',
        choices: [
          { label: 'Dragon', icon: '🐉', outcome: 'HP ticks down' },
          { label: 'Pebbles', icon: '🪨', outcome: 'Counts climb' },
        ],
      },
    };
    const onReady = vi.fn();
    const user = userEvent.setup();
    render(<ChoiceTrial entry={entry} onReady={onReady} />);

    await user.click(screen.getByRole('button', { name: /dragon/i }));
    expect(onReady).toHaveBeenCalledTimes(1);
    expect(screen.getByRole('button', { name: /pebbles/i })).toBeDisabled();
    expect(screen.getByText('Quest begins')).toBeInTheDocument();
  });
});

describe('DragToTargetTrial', () => {
  it('fires onReady once every source has been delivered', async () => {
    const entry = {
      trial: {
        prompt: 'Drag a coin.',
        payoff: 'Reward redeemed',
        source_count: 3,
        source_icon: '🪙',
        target_icon: '🎁',
      },
    };
    const onReady = vi.fn();
    const user = userEvent.setup();
    render(<DragToTargetTrial entry={entry} onReady={onReady} />);

    const send = screen.getByRole('button', { name: /send one/i });
    await user.click(send);
    await user.click(send);
    expect(onReady).not.toHaveBeenCalled();
    await user.click(send);
    expect(onReady).toHaveBeenCalledTimes(1);
    expect(screen.getByText('Reward redeemed')).toBeInTheDocument();
  });
});

describe('SequenceTrial', () => {
  it('advances through every step and fires onReady on the last one', async () => {
    const entry = {
      trial: {
        prompt: 'Hatch, feed, evolve.',
        payoff: 'Egg → Pet → Mount',
        steps: ['Combine egg + potion', 'Feed preferred food', 'Watch it evolve'],
      },
    };
    const onReady = vi.fn();
    const user = userEvent.setup();
    render(<SequenceTrial entry={entry} onReady={onReady} />);

    const advance = screen.getByRole('button', { name: /advance/i });
    await user.click(advance);
    await user.click(advance);
    expect(onReady).not.toHaveBeenCalled();
    await user.click(advance);
    expect(onReady).toHaveBeenCalledTimes(1);
    expect(screen.getByText(/egg → pet → mount/i)).toBeInTheDocument();
  });
});
