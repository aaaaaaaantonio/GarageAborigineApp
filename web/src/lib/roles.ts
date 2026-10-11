import type { Role } from '../api/types';

export const STAFF: Role[] = ['admin', 'master'];
export const ALL_ROLES: Role[] = ['admin', 'master', 'mechanic'];
/** Tab roots: no back button here. */
export const ROOT_PATHS = ['/visits', '/my', '/search', '/more'];

export function homePath(role: Role): string {
  return role === 'mechanic' ? '/my' : '/visits';
}
