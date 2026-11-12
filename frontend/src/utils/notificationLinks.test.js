import { describe, expect, it } from 'vitest';
import { notificationLinkSpace } from './notificationLinks';

describe('bounded notification workspace hints', () => {
  it.each([
    ['/quests?space=personal', 'personal'], ['/bestiary?tab=mounts&space=personal', 'personal'],
    ['/chores?space=personal', 'personal'], ['/chronicle?tab=journal&space=personal', 'personal'],
    ['/treasury?tab=hoards&space=personal', 'personal'], ['/family?child=7', 'family'],
    ['/family?space=family', 'family'], ['/chronicle?tab=journal&child=7&space=family', 'family'],
    ['/chronicle?tab=grades&child=7&space=family', 'family'],
    ['/projects/123?space=personal', 'personal'],
  ])('reads the known internal destination %s', (target, expected) => {
    expect(notificationLinkSpace(target)).toBe(expected);
  });

  it.each([
    '/manage?space=personal', '/family?space=personal', '/activity?space=personal',
    '/chronicle?tab=grades&space=personal', '/treasury?tab=coffers&space=personal',
    '/chronicle?tab=journal&space=family', '/chronicle?tab=journal&child=0&space=family',
    '/chronicle?tab=journal&child=7&child=8&space=family',
    '/quests?space=personal&space=family', '/quests?space=unknown',
    '/chronicle?tab=journal&tab=grades&space=personal',
    '/unknown?space=personal', 'https://outside.example/chores?space=personal',
    '//outside.example/chores?space=personal', '/\\outside.example/chores?space=personal',
    '/projects/0?space=personal', '/projects/-1?space=personal', '/projects/01?space=personal',
    '/projects/1.5?space=personal', '/projects/9007199254740992?space=personal',
    '/projects/1/other?space=personal', '/projects/new?space=personal',
  ])('ignores unsupported, external or ambiguous workspace hints: %s', target => {
    expect(notificationLinkSpace(target)).toBeNull();
  });
});
