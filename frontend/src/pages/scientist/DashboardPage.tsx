import { useEffect, useState, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Title, Text, SimpleGrid, Stack, Group, Paper, Table, Loader, Center,
  Timeline, Badge, Button, ThemeIcon,
} from '@mantine/core'
import {
  IconClipboardList, IconClock, IconLoader2, IconUserCheck, IconCertificate,
  IconRepeat, IconPlus, IconActivity,
} from '@tabler/icons-react'
import { api } from '../../api/client'
import { StatCard } from '../../components/StatCard'
import { StatusBadge } from '../../components/StatusBadge'
import type { DashboardData, SampleListItem } from '../../types'

export default function DashboardPage() {
  const navigate = useNavigate()
  const [dash, setDash] = useState<DashboardData | null>(null)
  const [samples, setSamples] = useState<SampleListItem[] | null>(null)

  const load = useCallback(async () => {
    const [d, s] = await Promise.all([api.get('/dashboard'), api.get('/samples')])
    setDash(d.data)
    // B7 (Review #2 remediation): GET /api/samples now returns
    // {total, samples} (pagination) instead of a bare array.
    setSamples(s.data.samples)
  }, [])

  useEffect(() => {
    load()
    const id = setInterval(load, 8000)
    return () => clearInterval(id)
  }, [load])

  if (!dash || !samples) {
    return <Center h={300}><Loader /></Center>
  }

  return (
    <Stack gap="lg">
      <Group justify="space-between">
        <Stack gap={0}>
          <Title order={2}>Scientist Dashboard</Title>
          <Text c="dimmed" size="sm">Overview of all cable samples in the laboratory</Text>
        </Stack>
        <Button leftSection={<IconPlus size={16} />} onClick={() => navigate('/samples/new')}>
          Register Sample
        </Button>
      </Group>

      <SimpleGrid cols={{ base: 2, md: 4 }} spacing="md">
        <StatCard label="Total Samples" value={dash.total_samples} icon={IconClipboardList} color="brandAccent" />
        <StatCard label="Pending" value={dash.pending} icon={IconClock} color="gray" />
        <StatCard label="In Progress" value={dash.in_progress} icon={IconLoader2} color="blue" />
        <StatCard label="Scientist Review" value={dash.scientist_review} icon={IconUserCheck} color="grape" />
        <StatCard label="Repeat Tests" value={dash.repeat_tests} icon={IconRepeat} color="orange" />
        <StatCard label="Certificates Issued" value={dash.certificates_issued} icon={IconCertificate} color="green" />
      </SimpleGrid>

      <SimpleGrid cols={{ base: 1, lg: 3 }} spacing="md">
        <Paper p="md" radius="lg" withBorder style={{ gridColumn: 'span 2' }}>
          <Group justify="space-between" mb="sm">
            <Text fw={700}>Samples</Text>
            <Text size="xs" c="dimmed">{samples.length} total</Text>
          </Group>
          <Table.ScrollContainer minWidth={560}>
            <Table verticalSpacing="sm" highlightOnHover>
              <Table.Thead>
                <Table.Tr>
                  <Table.Th>Sample ID</Table.Th>
                  <Table.Th>Standard</Table.Th>
                  <Table.Th>Profile</Table.Th>
                  <Table.Th>Tests</Table.Th>
                  <Table.Th>Status</Table.Th>
                </Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {samples.map((s) => (
                  <Table.Tr key={s.sample_id} style={{ cursor: 'pointer' }} onClick={() => navigate(`/samples/${s.sample_id}`)}>
                    <Table.Td fw={600}>{s.sample_id}</Table.Td>
                    <Table.Td>{s.standard ?? '—'}</Table.Td>
                    <Table.Td>
                      {s.profile ? (
                        <Group gap={4}>
                          <Badge size="xs" variant="light">{s.profile.conductor_material}</Badge>
                          <Badge size="xs" variant="light">{s.cores}C</Badge>
                          <Badge size="xs" variant="light">{s.csa_mm2}mm²</Badge>
                        </Group>
                      ) : <Text size="xs" c="dimmed">Awaiting profile</Text>}
                    </Table.Td>
                    <Table.Td>
                      <Text size="sm">{s.summary.completed_tests}/{s.summary.applicable_tests}</Text>
                    </Table.Td>
                    <Table.Td><StatusBadge status={s.status} size="sm" /></Table.Td>
                  </Table.Tr>
                ))}
                {samples.length === 0 && (
                  <Table.Tr><Table.Td colSpan={5}><Text c="dimmed" ta="center" py="lg">No samples yet &mdash; register the first one.</Text></Table.Td></Table.Tr>
                )}
              </Table.Tbody>
            </Table>
          </Table.ScrollContainer>
        </Paper>

        <Paper p="md" radius="lg" withBorder>
          <Group gap={6} mb="sm">
            <ThemeIcon variant="light" color="brandAccent" size={26}><IconActivity size={15} /></ThemeIcon>
            <Text fw={700}>Recent Activity</Text>
          </Group>
          <Timeline active={dash.recent_activity.length} bulletSize={16} lineWidth={2}>
            {dash.recent_activity.map((a, i) => (
              <Timeline.Item key={i} title={a.action.replace(/_/g, ' ')}>
                <Text size="xs" c="dimmed">{a.actor} &middot; {a.entity_id !== '-' ? a.entity_id : ''}</Text>
                <Text size="xs" c="dimmed">{new Date(a.timestamp).toLocaleString()}</Text>
              </Timeline.Item>
            ))}
            {dash.recent_activity.length === 0 && <Text size="sm" c="dimmed">No activity yet.</Text>}
          </Timeline>
        </Paper>
      </SimpleGrid>
    </Stack>
  )
}
