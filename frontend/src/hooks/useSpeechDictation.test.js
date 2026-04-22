import { act, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { useSpeechDictation } from './useSpeechDictation.js';

// Minimal stand-in for the browser SpeechRecognition API. Tests reach into
// `instance` to fire synthetic events so we can assert how the hook reacts.
function makeFakeRecognition() {
  let instance = null;
  class FakeRecognition {
    constructor() {
      this.continuous = false;
      this.interimResults = false;
      this.lang = '';
      this.onresult = null;
      this.onerror = null;
      this.onend = null;
      instance = this;
    }
    start() {
      this._running = true;
    }
    stop() {
      this._running = false;
      if (this.onend) this.onend();
    }
  }
  return {
    RecognitionClass: FakeRecognition,
    getInstance: () => instance,
  };
}

describe('useSpeechDictation', () => {
  let fake;
  beforeEach(() => {
    fake = makeFakeRecognition();
    // Stub both the prefixed + standard names.
    window.SpeechRecognition = fake.RecognitionClass;
    window.webkitSpeechRecognition = fake.RecognitionClass;
  });
  afterEach(() => {
    delete window.SpeechRecognition;
    delete window.webkitSpeechRecognition;
  });

  it('reports supported=true when the API exists', () => {
    const { result } = renderHook(() => useSpeechDictation({ onFinal: () => {} }));
    expect(result.current.supported).toBe(true);
    expect(result.current.isListening).toBe(false);
  });

  it('reports supported=false when the API is missing', () => {
    delete window.SpeechRecognition;
    delete window.webkitSpeechRecognition;
    const { result } = renderHook(() => useSpeechDictation({ onFinal: () => {} }));
    expect(result.current.supported).toBe(false);
  });

  it('start() flips isListening to true', () => {
    const { result } = renderHook(() => useSpeechDictation({ onFinal: () => {} }));
    act(() => result.current.start());
    expect(result.current.isListening).toBe(true);
  });

  it('final result fires onFinal with the transcript + trailing space', () => {
    const onFinal = vi.fn();
    const { result } = renderHook(() => useSpeechDictation({ onFinal }));
    act(() => result.current.start());
    const inst = fake.getInstance();
    act(() => {
      inst.onresult({
        resultIndex: 0,
        results: [
          Object.assign([{ transcript: 'hello world' }], {
            isFinal: true,
            0: { transcript: 'hello world' },
          }),
        ],
      });
    });
    expect(onFinal).toHaveBeenCalledWith('hello world ');
  });

  it('interim result updates the interim state but does not call onFinal', () => {
    const onFinal = vi.fn();
    const { result } = renderHook(() => useSpeechDictation({ onFinal }));
    act(() => result.current.start());
    const inst = fake.getInstance();
    act(() => {
      inst.onresult({
        resultIndex: 0,
        results: [
          Object.assign([{ transcript: 'still talking' }], {
            isFinal: false,
            0: { transcript: 'still talking' },
          }),
        ],
      });
    });
    expect(onFinal).not.toHaveBeenCalled();
    expect(result.current.interim).toBe('still talking');
  });

  it('stop() flips isListening to false', () => {
    const { result } = renderHook(() => useSpeechDictation({ onFinal: () => {} }));
    act(() => result.current.start());
    act(() => result.current.stop());
    expect(result.current.isListening).toBe(false);
  });

  it('onerror surfaces the error message and stops listening', () => {
    const { result } = renderHook(() => useSpeechDictation({ onFinal: () => {} }));
    act(() => result.current.start());
    const inst = fake.getInstance();
    act(() => inst.onerror({ error: 'not-allowed' }));
    expect(result.current.error).toBe('not-allowed');
    expect(result.current.isListening).toBe(false);
  });
});
