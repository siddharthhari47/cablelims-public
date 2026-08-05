import { useState } from 'react'
import { AppShell, Group, Text, NavLink, Box, Avatar, Menu, UnstyledButton } from '@mantine/core'
import { IconBolt, IconLayoutDashboard, IconPlus, IconChevronDown, IconLogout, IconFlask, IconShieldLock, IconKey } from '@tabler/icons-react'
import { useNavigate, useLocation, Outlet } from 'react-router-dom'
import { useAuthStore } from '../state/authStore'
import ChangePasswordModal from './ChangePasswordModal'

export default function DesktopShell() {
  const navigate = useNavigate()
  const location = useLocation()
  const { user, logout } = useAuthStore()
  const [changePasswordOpen, setChangePasswordOpen] = useState(false)

  const nav = [
    { label: 'Dashboard', icon: IconLayoutDashboard, path: '/dashboard' },
    { label: 'Register Sample', icon: IconPlus, path: '/samples/new' },
    ...(user?.role === 'ADMINISTRATOR' ? [{ label: 'Administration', icon: IconShieldLock, path: '/admin' }] : []),
  ]

  return (
    <AppShell header={{ height: 60 }} navbar={{ width: 240, breakpoint: 'sm' }} padding="md">
      <AppShell.Header style={{ background: '#0B2447' }}>
        <Group h="100%" px="md" justify="space-between">
          <Group gap="xs">
            <IconBolt color="white" size={22} />
            <Text c="white" fw={700} size="lg">CableLIMS</Text>
            <Text c="gray.5" size="sm" ml={4}>Cable Testing Laboratory</Text>
          </Group>
          <Menu shadow="md" width={200}>
            <Menu.Target>
              <UnstyledButton>
                <Group gap="xs">
                  <Avatar color="brandAccent" radius="xl" size={32}>
                    {user?.full_name?.[0] ?? '?'}
                  </Avatar>
                  <Box>
                    <Text c="white" size="sm" fw={600} lh={1.1}>{user?.full_name}</Text>
                    <Text c="gray.5" size="xs" lh={1.1}>{user?.role.replace('_', ' ')}</Text>
                  </Box>
                  <IconChevronDown size={14} color="white" />
                </Group>
              </UnstyledButton>
            </Menu.Target>
            <Menu.Dropdown>
              <Menu.Item leftSection={<IconKey size={14} />} onClick={() => setChangePasswordOpen(true)}>
                Change Password
              </Menu.Item>
              <Menu.Item leftSection={<IconLogout size={14} />} onClick={() => { logout(); navigate('/login') }}>
                Sign out
              </Menu.Item>
            </Menu.Dropdown>
          </Menu>
        </Group>
      </AppShell.Header>

      <AppShell.Navbar p="sm">
        {nav.map((item) => (
          <NavLink
            key={item.path}
            label={item.label}
            leftSection={<item.icon size={18} />}
            active={location.pathname === item.path}
            onClick={() => navigate(item.path)}
            mb={4}
            style={{ borderRadius: 8 }}
          />
        ))}
        <Box mt="auto" pt="xl">
          <Group gap={6} px="xs">
            <IconFlask size={14} color="gray" />
            <Text size="xs" c="dimmed">MVP Demonstration Build</Text>
          </Group>
        </Box>
      </AppShell.Navbar>

      <AppShell.Main style={{ background: '#f5f7fb' }}>
        <Outlet />
      </AppShell.Main>

      <ChangePasswordModal opened={changePasswordOpen} onClose={() => setChangePasswordOpen(false)} />
    </AppShell>
  )
}
