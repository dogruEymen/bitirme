import { useEffect } from 'react';
import type { ReactNode } from 'react';
import { Navigate, useLocation } from 'react-router-dom';
import { getStoredUser } from '../lib/auth';

interface RequireAuthProps {
  children: ReactNode;
}

export default function RequireAuth({ children }: RequireAuthProps) {
  const location = useLocation();
  const user = getStoredUser();

  useEffect(() => {
    if (!user) {
      window.localStorage.removeItem('academic_ai_user');
    }
  }, [user]);

  if (!user) {
    return <Navigate to="/auth" state={{ from: location }} replace />;
  }

  return <>{children}</>;
}
