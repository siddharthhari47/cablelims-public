import { Paper, Group, Text, ThemeIcon, Stack } from '@mantine/core'
import type { Icon as TablerIcon } from '@tabler/icons-react'

export function StatCard({
  label, value, icon: Icon, color = 'brandAccent', sub,
}: {
  label: string
  value: number | string
  icon: TablerIcon
  color?: string
  sub?: string
}) {
  return (
    <Paper p="md" radius="lg" withBorder>
      <Group justify="space-between" align="flex-start">
        <Stack gap={2}>
          <Text size="xs" c="dimmed" fw={600} tt="uppercase">{label}</Text>
          <Text size="28px" fw={700} lh={1.1}>{value}</Text>
          {sub && <Text size="xs" c="dimmed">{sub}</Text>}
        </Stack>
        <ThemeIcon size={42} radius="md" variant="light" color={color}>
          <Icon size={22} />
        </ThemeIcon>
      </Group>
    </Paper>
  )
}
