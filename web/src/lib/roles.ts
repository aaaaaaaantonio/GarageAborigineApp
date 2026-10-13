import type { Role } from '../api/types';

export const STAFF: Role[] = ['admin', 'master'];
export const ALL_ROLES: Role[] = ['admin', 'master', 'mechanic'];
/** Tab roots: no back button here. */
export const ROOT_PATHS = ['/visits', '/visits/new', '/my', '/my/done', '/search', '/more'];

/** Screens without the tab bar: leaving them goes through their own Cancel/Back. */
export const FULLSCREEN_PATHS = ['/visits/new'];

export function homePath(role: Role): string {
  return role === 'mechanic' ? '/my' : '/visits';
}
