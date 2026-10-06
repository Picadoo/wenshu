import { useState, useEffect } from 'react';

import { fetchVaultText } from 'src/data/vault-client';

export function useVaultText(path?: string) {
  const [source, setSource] = useState('');
  const [loading, setLoading] = useState(Boolean(path));
  const [error, setError] = useState('');

  useEffect(() => {
    if (!path) {
      setSource('');
      setLoading(false);
      setError('');
      return undefined;
    }

    let cancelled = false;
    setLoading(true);
    setError('');
    fetchVaultText(path)
      .then((value) => {
        if (cancelled) return;
        setSource(value);
        setLoading(false);
      })
      .catch((err: Error) => {
        if (cancelled) return;
        setSource('');
        setError(err.message);
        setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [path]);

  return { source, loading, error };
}
