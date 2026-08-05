import { useEffect, useState } from 'react'
import {
  Stack, Title, Text, Tabs, Table, Badge, Button, Group, Modal, TextInput, PasswordInput,
  Select, Switch, ActionIcon, Tooltip, Paper, ScrollArea, Code,
} from '@mantine/core'
import { notifications } from '@mantine/notifications'
import { IconUserPlus, IconEdit, IconShieldLock, IconHistory, IconUsers } from '@tabler/icons-react'
import { api, extractErrorMessage } from '../../api/client'
import { useAuthStore } from '../../state/authStore'

interface AdminUser {
  id: string; username: string; full_name: string; role: string
  is_active: boolean; is_demo: boolean; created_at: string
}
interface AuditEventRow {
  id: string; actor_name: string; action: string; entity_type: string | null
  entity_id: string | null; details: Record<string, unknown>; timestamp: string
}

const ROLES = ['SCIENTIST', 'SCIENTIFIC_ASSISTANT', 'ADMINISTRATOR']

export default function AdminPage() {
  const currentUser = useAuthStore((s) => s.user)
  const [users, setUsers] = useState<AdminUser[]>([])
  const [audit, setAudit] = useState<AuditEventRow[]>([])
  const [createOpen, setCreateOpen] = useState(false)
  const [editUser, setEditUser] = useState<AdminUser | null>(null)

  const load = () => {
    api.get('/admin/users').then((r) => setUsers(r.data))
    api.get('/admin/audit', { params: { limit: 100 } }).then((r) => setAudit(r.data.events))
  }
  useEffect(load, [])

  return (
    <Stack gap="md">
      <Title order={2}>Administration</Title>
      <Text c="dimmed" size="sm">Manage accounts, roles, and review the activity log.</Text>

      <Tabs defaultValue="users" keepMounted={false}>
        <Tabs.List>
          <Tabs.Tab value="users" leftSection={<IconUsers size={16} />}>Users</Tabs.Tab>
          <Tabs.Tab value="audit" leftSection={<IconHistory size={16} />}>Audit Log</Tabs.Tab>
        </Tabs.List>

        <Tabs.Panel value="users" pt="md">
          <Paper p="md" radius="lg" withBorder>
            <Group justify="space-between" mb="md">
              <Text fw={700}>User Accounts</Text>
              <Button size="sm" leftSection={<IconUserPlus size={16} />} onClick={() => setCreateOpen(true)}>
                Create User
              </Button>
            </Group>
            <Table.ScrollContainer minWidth={600}>
              <Table verticalSpacing="sm" highlightOnHover>
                <Table.Thead>
                  <Table.Tr>
                    <Table.Th>Username</Table.Th>
                    <Table.Th>Full Name</Table.Th>
                    <Table.Th>Role</Table.Th>
                    <Table.Th>Status</Table.Th>
                    <Table.Th></Table.Th>
                  </Table.Tr>
                </Table.Thead>
                <Table.Tbody>
                  {users.map((u) => (
                    <Table.Tr key={u.id}>
                      <Table.Td>
                        <Group gap={6}>
                          <Text size="sm">{u.username}</Text>
                          {u.is_demo && <Badge size="xs" color="gray" variant="light">Demo</Badge>}
                          {u.id === currentUser?.id && <Badge size="xs" color="blue" variant="light">You</Badge>}
                        </Group>
                      </Table.Td>
                      <Table.Td><Text size="sm">{u.full_name}</Text></Table.Td>
                      <Table.Td><Badge size="sm" variant="light">{u.role.replace('_', ' ')}</Badge></Table.Td>
                      <Table.Td>
                        <Badge size="sm" color={u.is_active ? 'green' : 'red'} variant="light">
                          {u.is_active ? 'Active' : 'Deactivated'}
                        </Badge>
                      </Table.Td>
                      <Table.Td>
                        <Tooltip label="Edit / reset password / role">
                          <ActionIcon variant="light" onClick={() => setEditUser(u)}>
                            <IconEdit size={14} />
                          </ActionIcon>
                        </Tooltip>
                      </Table.Td>
                    </Table.Tr>
                  ))}
                </Table.Tbody>
              </Table>
            </Table.ScrollContainer>
          </Paper>
        </Tabs.Panel>

        <Tabs.Panel value="audit" pt="md">
          <Paper p="md" radius="lg" withBorder>
            <Group gap={6} mb="md">
              <IconShieldLock size={16} color="gray" />
              <Text fw={700}>Activity Log</Text>
              <Text size="xs" c="dimmed">most recent 100 events</Text>
            </Group>
            <ScrollArea h={520}>
              <Table verticalSpacing="xs" fz="xs">
                <Table.Thead>
                  <Table.Tr>
                    <Table.Th>When</Table.Th>
                    <Table.Th>Actor</Table.Th>
                    <Table.Th>Action</Table.Th>
                    <Table.Th>Entity</Table.Th>
                    <Table.Th>Details</Table.Th>
                  </Table.Tr>
                </Table.Thead>
                <Table.Tbody>
                  {audit.map((e) => (
                    <Table.Tr key={e.id}>
                      <Table.Td>{new Date(e.timestamp).toLocaleString()}</Table.Td>
                      <Table.Td>{e.actor_name}</Table.Td>
                      <Table.Td><Badge size="xs" variant="light">{e.action}</Badge></Table.Td>
                      <Table.Td>{e.entity_type}{e.entity_id ? ` · ${e.entity_id.slice(0, 8)}` : ''}</Table.Td>
                      <Table.Td>
                        {e.details && Object.keys(e.details).length > 0 && (
                          <Code fz={10}>{JSON.stringify(e.details)}</Code>
                        )}
                      </Table.Td>
                    </Table.Tr>
                  ))}
                </Table.Tbody>
              </Table>
            </ScrollArea>
          </Paper>
        </Tabs.Panel>
      </Tabs>

      <CreateUserModal opened={createOpen} onClose={() => setCreateOpen(false)} onCreated={load} />
      <EditUserModal user={editUser} onClose={() => setEditUser(null)} onSaved={load} />
    </Stack>
  )
}

function CreateUserModal({ opened, onClose, onCreated }: { opened: boolean; onClose: () => void; onCreated: () => void }) {
  const [username, setUsername] = useState('')
  const [fullName, setFullName] = useState('')
  const [role, setRole] = useState<string | null>('SCIENTIST')
  const [password, setPassword] = useState('')
  const [saving, setSaving] = useState(false)

  async function submit() {
    setSaving(true)
    try {
      await api.post('/admin/users', { username, full_name: fullName, role, password })
      notifications.show({ title: 'User created', message: username, color: 'green' })
      setUsername(''); setFullName(''); setPassword(''); setRole('SCIENTIST')
      onCreated()
      onClose()
    } catch (err: unknown) {
      notifications.show({ title: 'Could not create user', message: extractErrorMessage(err), color: 'red' })
    } finally {
      setSaving(false)
    }
  }

  return (
    <Modal opened={opened} onClose={onClose} title="Create User" centered>
      <Stack gap="sm">
        <TextInput label="Username" value={username} onChange={(e) => setUsername(e.currentTarget.value)} required />
        <TextInput label="Full Name" value={fullName} onChange={(e) => setFullName(e.currentTarget.value)} required />
        <Select label="Role" data={ROLES} value={role} onChange={setRole} allowDeselect={false} required />
        <PasswordInput label="Password" description="At least 8 characters" value={password} onChange={(e) => setPassword(e.currentTarget.value)} required />
        <Button mt="xs" onClick={submit} loading={saving} disabled={!username || !fullName || !role || password.length < 8}>
          Create Account
        </Button>
      </Stack>
    </Modal>
  )
}

function EditUserModal({ user, onClose, onSaved }: { user: AdminUser | null; onClose: () => void; onSaved: () => void }) {
  const [fullName, setFullName] = useState('')
  const [role, setRole] = useState<string | null>(null)
  const [isActive, setIsActive] = useState(true)
  const [newPassword, setNewPassword] = useState('')
  const [saving, setSaving] = useState(false)

  const key = user?.id ?? ''
  const [lastKey, setLastKey] = useState('')
  if (key !== lastKey) {
    setLastKey(key)
    setFullName(user?.full_name ?? '')
    setRole(user?.role ?? null)
    setIsActive(user?.is_active ?? true)
    setNewPassword('')
  }

  async function submit() {
    if (!user) return
    setSaving(true)
    try {
      const body: Record<string, unknown> = { full_name: fullName, role, is_active: isActive }
      if (newPassword) body.password = newPassword
      await api.patch(`/admin/users/${user.id}`, body)
      notifications.show({ title: 'User updated', message: user.username, color: 'green' })
      onSaved()
      onClose()
    } catch (err: unknown) {
      notifications.show({ title: 'Could not update user', message: extractErrorMessage(err), color: 'red' })
    } finally {
      setSaving(false)
    }
  }

  return (
    <Modal opened={!!user} onClose={onClose} title={user ? `Edit ${user.username}` : ''} centered>
      {user && (
        <Stack gap="sm">
          <TextInput label="Full Name" value={fullName} onChange={(e) => setFullName(e.currentTarget.value)} />
          <Select label="Role" data={ROLES} value={role} onChange={setRole} allowDeselect={false} />
          <Switch label="Account active" checked={isActive} onChange={(e) => setIsActive(e.currentTarget.checked)} />
          <PasswordInput
            label="Reset password (optional)" description="Leave blank to keep the current password"
            value={newPassword} onChange={(e) => setNewPassword(e.currentTarget.value)}
          />
          <Button mt="xs" onClick={submit} loading={saving} disabled={newPassword.length > 0 && newPassword.length < 8}>
            Save Changes
          </Button>
        </Stack>
      )}
    </Modal>
  )
}
