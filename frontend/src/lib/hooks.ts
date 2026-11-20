import { useCallback, useEffect, useRef, useState } from "react";

/** Load data on mount (and when deps change); exposes loading/error/reload. */
export function useLoad<T>(fn: () => Promise<T>, deps: unknown[] = []) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const fnRef = useRef(fn);
  fnRef.current = fn;
  const reload = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setData(await fnRef.current());
    } catch (e: any) {
      setError(e?.message ?? String(e));
    } finally {
      setLoading(false);
    }
  }, []);
  useEffect(() => {
    reload();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
  return { data, error, loading, reload, setData };
}

/** Wrap an async action with busy/error state. */
export function useAction<A extends unknown[], T>(fn: (...args: A) => Promise<T>) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<T | null>(null);
  const run = useCallback(
    async (...args: A) => {
      setBusy(true);
      setError(null);
      try {
        const r = await fn(...args);
        setResult(r);
        return r;
      } catch (e: any) {
        setError(e?.message ?? String(e));
        return null;
      } finally {
        setBusy(false);
      }
    },
    [fn],
  );
  return { run, busy, error, result, setResult };
}
