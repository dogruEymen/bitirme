export interface AuthUser {
  id: string;
  username: string;
  email: string;
}

const STORAGE_KEY = 'academic_ai_user';

export function getStoredUser(): AuthUser | null {
  if (typeof window === 'undefined') return null;
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const user = JSON.parse(raw) as Partial<AuthUser>;
    if (
      typeof user.id !== 'string' ||
      typeof user.username !== 'string' ||
      typeof user.email !== 'string'
    ) {
      window.localStorage.removeItem(STORAGE_KEY);
      return null;
    }
    return user as AuthUser;
  } catch {
    window.localStorage.removeItem(STORAGE_KEY);
    return null;
  }
}

export function setStoredUser(user: AuthUser) {
  if (typeof window === 'undefined') return;
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify(user));
}

export function clearStoredUser() {
  if (typeof window === 'undefined') return;
  window.localStorage.removeItem(STORAGE_KEY);
}

export function getAuthHeaders(): Record<string, string> {
  const user = getStoredUser();
  return user ? { 'X-User-Id': user.id } : {};
}
