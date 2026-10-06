import { useNavigate } from 'react-router';
import { useMemo } from 'react';

export function useRouter() {
  const navigate = useNavigate();
  return useMemo(() => ({ push: (to: string) => navigate(to), replace: (to: string) => navigate(to, { replace: true }), back: () => navigate(-1) }), [navigate]);
}
