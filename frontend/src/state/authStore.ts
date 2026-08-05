import { create } from 'zustand'
import { persist, createJSONStorage } from 'zustand/middleware'

export type Role = 'SCIENTIST' | 'SCIENTIFIC_ASSISTANT' | 'ADMINISTRATOR'

export interface AuthUser {
  id: string
  username: string
  full_name: string
  role: Role
}

interface AuthState {
  token: string | null
  user: AuthUser | null
  // Offline support, phase 5: whether this login should also survive a
  // fully offline cold-launch of the installed PWA -- see the storage
  // comment below for what this does and doesn't change.
  stayLoggedIn: boolean
  // `stayLoggedIn` is optional here on purpose: LoginPage.tsx (a fresh,
  // deliberate choice) always passes it explicitly; ChangePasswordModal.tsx
  // (swapping in a renewed token, not a new login decision) omits it, which
  // preserves whatever the session's existing setting already was rather
  // than silently resetting it to off.
  login: (token: string, user: AuthUser, stayLoggedIn?: boolean) => void
  logout: () => void
  setStayLoggedIn: (value: boolean) => void
}

// Separate from the zustand-persisted `cablelims-auth` sessionStorage entry
// below -- this is the ONLY thing ever written to localStorage for auth, and
// only when both persistToStandalone() preconditions hold.
const STANDALONE_KEY = 'cablelims-auth-standalone'

export function isStandaloneDisplay(): boolean {
  return typeof window !== 'undefined' && typeof window.matchMedia === 'function'
    && window.matchMedia('(display-mode: standalone)').matches
}

function writeStandaloneCopy(token: string, user: AuthUser): void {
  try {
    localStorage.setItem(STANDALONE_KEY, JSON.stringify({ token, user }))
  } catch {
    // localStorage can throw (private browsing storage caps, etc.) --
    // non-fatal: "stay signed in" just silently doesn't survive a cold
    // launch this time, the same as if the toggle had been off.
  }
}

function clearStandaloneCopy(): void {
  try {
    localStorage.removeItem(STANDALONE_KEY)
  } catch {
    // see writeStandaloneCopy
  }
}

export function readStandaloneCopy(): { token: string; user: AuthUser } | null {
  try {
    const raw = localStorage.getItem(STANDALONE_KEY)
    if (!raw) return null
    const parsed = JSON.parse(raw)
    if (typeof parsed?.token !== 'string' || !parsed?.user) return null
    return parsed
  } catch {
    return null
  }
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set, get) => ({
      token: null,
      user: null,
      stayLoggedIn: false,
      login: (token, user, stayLoggedIn) => {
        const effective = stayLoggedIn ?? get().stayLoggedIn
        set({ token, user, stayLoggedIn: effective })
        if (effective && isStandaloneDisplay()) writeStandaloneCopy(token, user)
        else clearStandaloneCopy()
      },
      logout: () => {
        set({ token: null, user: null, stayLoggedIn: false })
        clearStandaloneCopy()
      },
      setStayLoggedIn: (value) => {
        const { token, user } = get()
        set({ stayLoggedIn: value })
        if (value && token && user && isStandaloneDisplay()) writeStandaloneCopy(token, user)
        else clearStandaloneCopy()
      },
    }),
    {
      name: 'cablelims-auth',
      // sessionStorage, not localStorage: a login must not silently carry
      // over to a brand-new tab or window -- each one starts its own empty
      // session and has to authenticate again. localStorage is shared
      // across every tab of the same origin, which is exactly the gap that
      // let a new tab stay logged in without re-entering credentials. A
      // same-tab refresh still keeps you logged in (sessionStorage survives
      // reload); only a genuinely new tab/window, or closing this one, ends it.
      //
      // Offline support, phase 5: this sessionStorage-only behavior is
      // UNCHANGED for the normal browser-tab case -- a new tab still forces
      // login, exactly as before. The only way auth survives a fresh
      // top-level context is the separate `cablelims-auth-standalone`
      // localStorage entry above, and that is written ONLY when the user
      // explicitly opts in (the "Stay signed in on this device" toggle,
      // default off) AND the app is actually running as an installed,
      // standalone-mode PWA right now -- never for an ordinary browser tab,
      // regardless of the toggle. See rehydrateFromStandaloneCopy() in
      // main.tsx, called once at boot, for the other half of this.
      storage: createJSONStorage(() => sessionStorage),
    },
  ),
)

// Called once at app boot (main.tsx), before the router renders anything.
// If this tab's sessionStorage already has a session (the normal case --
// same-tab reload, or a fresh login moments ago), there's nothing to do.
// Otherwise, if we're genuinely running as an installed standalone PWA
// right now AND an opted-in copy exists in localStorage, rehydrate from
// it -- this is the one thing that lets the installed app survive being
// closed and relaunched with zero network available to log in again.
export function rehydrateFromStandaloneCopy(): void {
  if (useAuthStore.getState().token) return
  if (!isStandaloneDisplay()) return
  const saved = readStandaloneCopy()
  if (saved) useAuthStore.setState({ token: saved.token, user: saved.user, stayLoggedIn: true })
}
