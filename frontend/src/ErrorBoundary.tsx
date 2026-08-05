import { Component, type ReactNode } from 'react'

export class ErrorBoundary extends Component<{ children: ReactNode }, { error: Error | null }> {
  constructor(props: { children: ReactNode }) {
    super(props)
    this.state = { error: null }
  }
  static getDerivedStateFromError(error: Error) {
    return { error }
  }
  componentDidCatch(error: Error, info: { componentStack?: string | null }) {
    // Full detail belongs in the console for whoever's debugging -- the
    // on-screen fallback below stays free of raw stack traces since real
    // CTL staff, not just developers, will see it if this ever fires.
    console.error('CableLIMS crashed:', error, info.componentStack)
  }
  render() {
    if (this.state.error) {
      return (
        <div style={{ padding: 32, maxWidth: 480, margin: '10vh auto', textAlign: 'center', fontFamily: 'sans-serif' }}>
          <h2 style={{ marginBottom: 8 }}>Something went wrong</h2>
          <p style={{ color: '#555', marginBottom: 20 }}>
            This screen hit an unexpected error and can't continue. Reloading usually fixes it; if it keeps
            happening, please note what you were doing and let the team know.
          </p>
          <button
            onClick={() => window.location.reload()}
            style={{ padding: '10px 20px', background: '#19376D', color: 'white', border: 'none', borderRadius: 6, cursor: 'pointer' }}
          >
            Reload
          </button>
        </div>
      )
    }
    return this.props.children
  }
}
