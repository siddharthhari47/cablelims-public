import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { MantineProvider } from '@mantine/core'
import { Notifications } from '@mantine/notifications'
import { BrowserRouter } from 'react-router-dom'
import { registerSW } from 'virtual:pwa-register'

import '@mantine/core/styles.css'
import '@mantine/notifications/styles.css'
import './index.css'

import App from './App.tsx'
import { theme } from './theme.ts'
import { ErrorBoundary } from './ErrorBoundary.tsx'
import { rehydrateFromStandaloneCopy } from './state/authStore.ts'

// Offline support, phase 1: installable app shell only -- registers the
// service worker that precaches the built JS/CSS/HTML (see vite.config.ts).
// autoUpdate means a new deployed build takes over silently on next load,
// no user-facing "update available" prompt is wired up (this app is a
// single-lab appliance the operator restarts, not a public site with users
// mid-session across deploys).
registerSW({ immediate: true })

// Offline support, phase 5: must run before the first render -- if this is
// an installed PWA being relaunched with an empty sessionStorage (the app
// was fully closed) and the user previously opted into "Stay signed in on
// this device," this restores the session synchronously so ProtectedRoute's
// very first check sees it, instead of a flash of the login screen.
rehydrateFromStandaloneCopy()

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ErrorBoundary>
      <MantineProvider theme={theme} defaultColorScheme="light">
        <Notifications position="top-right" />
        <BrowserRouter>
          <App />
        </BrowserRouter>
      </MantineProvider>
    </ErrorBoundary>
  </StrictMode>,
)
