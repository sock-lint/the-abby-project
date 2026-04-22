import { useCallback, useEffect, useRef, useState } from 'react';

/**
 * Wraps the browser Web Speech API for live dictation.
 *
 * Usage:
 *   const { start, stop, isListening, interim, supported, error }
 *     = useSpeechDictation({ onFinal: (chunk) => append(chunk) });
 *
 * Final chunks arrive with a trailing space so repeated appends read as
 * natural prose. Interim results are exposed as a separate string so
 * callers can render "still transcribing…" feedback without mutating the
 * underlying text.
 */
export function useSpeechDictation({ onFinal, lang } = {}) {
  const SpeechRecognition =
    typeof window === 'undefined'
      ? null
      : window.SpeechRecognition || window.webkitSpeechRecognition || null;

  const supported = Boolean(SpeechRecognition);
  const [isListening, setIsListening] = useState(false);
  const [interim, setInterim] = useState('');
  const [error, setError] = useState(null);
  const recognitionRef = useRef(null);
  const onFinalRef = useRef(onFinal);

  // Keep the latest callback without re-wiring the recognition instance
  // every render.
  useEffect(() => {
    onFinalRef.current = onFinal;
  }, [onFinal]);

  const start = useCallback(() => {
    if (!supported) return;
    if (recognitionRef.current) return;
    const recognition = new SpeechRecognition();
    recognition.continuous = true;
    recognition.interimResults = true;
    recognition.lang =
      lang || (typeof navigator !== 'undefined' && navigator.language) || 'en-US';

    recognition.onresult = (event) => {
      let finalChunk = '';
      let interimChunk = '';
      for (let i = event.resultIndex; i < event.results.length; i += 1) {
        const res = event.results[i];
        const text = res[0]?.transcript ?? '';
        if (res.isFinal) {
          finalChunk += text;
        } else {
          interimChunk += text;
        }
      }
      if (finalChunk) {
        setInterim('');
        onFinalRef.current?.(`${finalChunk} `);
      } else {
        setInterim(interimChunk);
      }
    };
    recognition.onerror = (event) => {
      setError(event?.error || 'unknown');
      setIsListening(false);
      recognitionRef.current = null;
    };
    recognition.onend = () => {
      setIsListening(false);
      setInterim('');
      recognitionRef.current = null;
    };

    recognitionRef.current = recognition;
    setError(null);
    setInterim('');
    setIsListening(true);
    recognition.start();
  }, [SpeechRecognition, lang, supported]);

  const stop = useCallback(() => {
    const recognition = recognitionRef.current;
    if (recognition) recognition.stop();
    setIsListening(false);
    setInterim('');
  }, []);

  // Clean up if the component unmounts mid-transcription.
  useEffect(() => () => {
    const recognition = recognitionRef.current;
    if (recognition) {
      try {
        recognition.stop();
      } catch {
        // ignore
      }
    }
  }, []);

  return { start, stop, isListening, interim, supported, error };
}
