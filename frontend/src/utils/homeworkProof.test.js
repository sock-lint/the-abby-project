import { describe, expect, it } from 'vitest';
import { getHomeworkProofUrl } from './homeworkProof';

describe('getHomeworkProofUrl', () => {
  it.each([
    'https://drive.google.com/file/d/synthetic-proof/view?usp=sharing#page=1',
    'http://example.test/completed-work',
  ])('preserves a complete HTTP(S) link without changing its query or fragment: %s', (url) => {
    expect(getHomeworkProofUrl(`  ${url}  `)).toBe(url);
  });

  it.each([
    null, undefined, 42, '', '   ', 'not a URL', '/proof', '//example.test/proof',
    'javascript:alert(1)', 'data:text/html,proof', 'ftp://example.test/proof', 'https:example.test/proof',
    'https://user:password@example.test/proof', 'https://example.test/proof with spaces',
    'https://example.test/proof\n', 'https://example.test/proof\u007f',
    `https://example.test/${'a'.repeat(2048)}`,
  ])('rejects an unsafe or malformed proof link: %s', (url) => {
    expect(getHomeworkProofUrl(url)).toBe('');
  });

  it('accepts a URL at the supported length limit', () => {
    const url = `https://example.test/${'a'.repeat(2048 - 'https://example.test/'.length)}`;
    expect(getHomeworkProofUrl(url)).toBe(url);
  });
});
