import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { Paper, TextInput, PasswordInput, Button, Title, Text, Stack, Alert, Center, Box, Checkbox } from '@mantine/core'
import { IconAlertCircle, IconBolt } from '@tabler/icons-react'
import { api } from '../api/client'
import { useAuthStore, isStandaloneDisplay } from '../state/authStore'

export default function LoginPage() {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [showDemoHint, setShowDemoHint] = useState(false)
  const [stayLoggedIn, setStayLoggedIn] = useState(false)
  const navigate = useNavigate()
  const login = useAuthStore((s) => s.login)

  // Offline support, phase 5: only offered when it would actually do
  // something -- the underlying mechanism only ever persists in
  // display-mode: standalone (see authStore.ts), so showing this to a
  // Scientist in an ordinary desktop browser tab would just be a checkbox
  // that silently does nothing, which reads as broken rather than N/A.
  const showStayLoggedIn = isStandaloneDisplay()

  useEffect(() => {
    // A real install (account created via create_user.py) never has these
    // demo accounts -- showing this hint unconditionally told people to log
    // in with credentials that don't exist there, which just reads as a bug.
    api.get('/auth/demo-hint').then((res) => setShowDemoHint(res.data.show_demo_hint)).catch(() => {})
  }, [])

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError(null)
    setLoading(true)
    try {
      const res = await api.post('/auth/login', { username, password })
      login(res.data.access_token, res.data.user, showStayLoggedIn && stayLoggedIn)
      const role = res.data.user.role
      if (role === 'SCIENTIFIC_ASSISTANT') navigate('/assistant')
      else navigate('/dashboard')
    } catch {
      setError('Invalid username or password.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <Center style={{ minHeight: '100svh', background: 'linear-gradient(160deg,#0B2447 0%,#19376D 55%,#12335e 100%)' }}>
      <Paper radius="lg" p="xl" shadow="xl" style={{ width: 380, maxWidth: '92vw' }}>
        <Stack align="center" gap={4} mb="lg">
          <Box
            style={{
              width: 52, height: 52, borderRadius: 12, background: '#0B2447',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
            }}
          >
            <IconBolt color="white" size={28} />
          </Box>
          <Title order={2} mt="xs" ta="center">CableLIMS</Title>
          <Text size="sm" c="dimmed" ta="center">Cable Testing Laboratory</Text>
        </Stack>

        <form onSubmit={handleSubmit}>
          <Stack gap="sm">
            {error && (
              <Alert color="red" icon={<IconAlertCircle size={16} />}>{error}</Alert>
            )}
            <TextInput
              label="Username" placeholder="scientist1" value={username} autoFocus
              onChange={(e) => setUsername(e.currentTarget.value)} required
            />
            <PasswordInput
              label="Password" placeholder="••••••••" value={password}
              onChange={(e) => setPassword(e.currentTarget.value)} required
            />
            {showStayLoggedIn && (
              <Checkbox
                label="Stay signed in on this device"
                description="Keeps you logged in even if the app is fully closed with no connection. Only turn this on for a device that's yours alone."
                checked={stayLoggedIn}
                onChange={(e) => setStayLoggedIn(e.currentTarget.checked)}
              />
            )}
            <Button type="submit" fullWidth mt="sm" loading={loading}>Sign in</Button>
          </Stack>
        </form>

        {showDemoHint && (
          <Text size="xs" c="dimmed" mt="lg" ta="center">
            Demo accounts &mdash; password <b>demo1234</b><br />
            scientist1 (Scientist) &middot; assistant1 (Scientific Assistant) &middot; admin1 (Administrator)
          </Text>
        )}
      </Paper>
    </Center>
  )
}
