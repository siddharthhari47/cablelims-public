import { useState } from 'react'
import { Box, Group, Text, Avatar, Menu } from '@mantine/core'
import { IconBolt, IconLogout, IconKey, IconDeviceMobile, IconDeviceMobileOff } from '@tabler/icons-react'
import { useNavigate, Outlet } from 'react-router-dom'
import { useAuthStore, isStandaloneDisplay } from '../state/authStore'
import ChangePasswordModal from './ChangePasswordModal'
import { SyncStatusBadge } from '../offline/SyncStatusPanel'

export default function MobileShell() {
  const navigate = useNavigate()
  const { user, logout, stayLoggedIn, setStayLoggedIn } = useAuthStore()
  const [changePasswordOpen, setChangePasswordOpen] = useState(false)
  // Same visibility rule as LoginPage.tsx's checkbox -- only shown where
  // the underlying mechanism actually does anything.
  const showStayLoggedInToggle = isStandaloneDisplay()

  return (
    <Box style={{ minHeight: '100svh', background: '#f5f7fb', display: 'flex', flexDirection: 'column' }}>
      <Box
        style={{
          background: '#0B2447', position: 'sticky', top: 0, zIndex: 100,
          paddingTop: 'env(safe-area-inset-top)',
        }}
      >
        <Group justify="space-between" px="md" py="sm">
          <Group gap={8}>
            <IconBolt color="white" size={20} />
            <Text c="white" fw={700}>CableLIMS</Text>
          </Group>
          <Group gap={8}>
            <SyncStatusBadge />
            <Menu shadow="md" width={200} position="bottom-end">
              <Menu.Target>
                <Avatar color="brandAccent" radius="xl" size={30} style={{ cursor: 'pointer' }}>
                  {user?.full_name?.[0] ?? '?'}
                </Avatar>
              </Menu.Target>
              <Menu.Dropdown>
                <Menu.Item leftSection={<IconKey size={14} />} onClick={() => setChangePasswordOpen(true)}>
                  Change Password
                </Menu.Item>
                {showStayLoggedInToggle && (
                  <Menu.Item
                    leftSection={stayLoggedIn ? <IconDeviceMobileOff size={14} /> : <IconDeviceMobile size={14} />}
                    onClick={() => setStayLoggedIn(!stayLoggedIn)}
                  >
                    {stayLoggedIn ? 'Stop staying signed in' : 'Stay signed in on this device'}
                  </Menu.Item>
                )}
                <Menu.Item leftSection={<IconLogout size={14} />} onClick={() => { logout(); navigate('/login') }}>
                  Sign out
                </Menu.Item>
              </Menu.Dropdown>
            </Menu>
          </Group>
        </Group>
      </Box>
      <Box style={{ flex: 1, paddingBottom: 24 }}>
        <Outlet />
      </Box>

      <ChangePasswordModal opened={changePasswordOpen} onClose={() => setChangePasswordOpen(false)} />
    </Box>
  )
}
