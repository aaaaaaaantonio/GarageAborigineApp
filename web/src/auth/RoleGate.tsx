import type { ReactNode } from 'react';
import type { Role } from '../api/types';
import { NoAccessScreen } from '../screens/NoAccessScreen';
import { useAuth } from './AuthProvider';

export function RoleGate({ roles, children }: { roles: Role[]; children: ReactNode }) {
  const { user } = useAuth();
  if (!user || !roles.includes(user.role)) return <NoAccessScreen />;
  return <>{children}</>;
}
