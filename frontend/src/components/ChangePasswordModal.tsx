import { useState } from 'react'
import { Modal, Stack, PasswordInput, Button, Text } from '@mantine/core'
import { notifications } from '@mantine/notifications'
import { api, extractErrorMessage } from '../api/client'
import { useAuthStore } from '../state/authStore'

export default function ChangePasswordModal({ opened, onClose }: { opened: boolean; onClose: () => void }) {
  const [currentPassword, setCurrentPassword] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [saving, setSaving] = useState(false)
  const login = useAuthStore((s) => s.login)

  function reset() {
    setCurrentPassword('')
    setNewPassword('')
    setConfirmPassword('')
  }

  function close() {
    reset()
    onClose()
  }

  async function submit() {
    if (newPassword !== confirmPassword) {
      notifications.show({ title: 'Passwords do not match', message: 'Re-enter the new password the same way twice.', color: 'red' })
      return
    }
    setSaving(true)
    try {
      const resp = await api.post('/auth/change-password', {
        current_password: currentPassword, new_password: newPassword,
      })
      // The backend invalidates the token this request was made with the
      // moment the password changes (H6) and hands back a fresh one in the
      // same response -- swap it in immediately or the very next request
      // this tab makes would 401 and force an unwanted logout.
      login(resp.data.access_token, resp.data.user)
      notifications.show({
        title: 'Password changed',
        message: 'Your password has been updated. Any other signed-in device has been signed out.',
        color: 'green',
      })
      close()
    } catch (err: unknown) {
      notifications.show({ title: 'Could not change password', message: extractErrorMessage(err), color: 'red' })
    } finally {
      setSaving(false)
    }
  }

  return (
    <Modal opened={opened} onClose={close} title="Change Password" centered>
      <Stack gap="sm">
        <PasswordInput
          label="Current Password" value={currentPassword}
          onChange={(e) => setCurrentPassword(e.currentTarget.value)} required
        />
        <PasswordInput
          label="New Password" description="At least 8 characters" value={newPassword}
          onChange={(e) => setNewPassword(e.currentTarget.value)} required
        />
        <PasswordInput
          label="Confirm New Password" value={confirmPassword}
          onChange={(e) => setConfirmPassword(e.currentTarget.value)} required
        />
        <Text size="xs" c="dimmed">Changing your password signs you out on every other device.</Text>
        <Button
          mt="xs" onClick={submit} loading={saving}
          disabled={!currentPassword || newPassword.length < 8 || !confirmPassword}
        >
          Change Password
        </Button>
      </Stack>
    </Modal>
  )
}
