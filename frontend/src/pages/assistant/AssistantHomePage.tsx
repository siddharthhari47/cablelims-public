import { useEffect, useState, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { Stack, Text, Card, Group, Loader, Center, Title, Box, Tooltip } from '@mantine/core'
import { IconArrowBack, IconChevronRight, IconPlugConnected } from '@tabler/icons-react'
import { api } from '../../api/client'
import { StatusBadge } from '../../components/StatusBadge'
import { getCachedSamples, putCachedSamples } from '../../offline/db'
import { OfflineBanner } from '../../offline/OfflineBanner'
import { isNetworkError } from '../../offline/isNetworkError'
import { runSyncPass } from '../../offline/syncEngine'
import type { SampleListItem } from '../../types'

export default function AssistantHomePage() {
  const navigate = useNavigate()
  const [samples, setSamples] = useState<SampleListItem[] | null>(null)
  const [cachedAt, setCachedAt] = useState<number | null>(null)
  const [loadError, setLoadError] = useState(false)

  const load = useCallback(async () => {
    try {
      const res = await api.get('/samples')
      // B7 (Review #2 remediation): GET /api/samples now returns
      // {total, samples} (pagination) instead of a bare array.
      setSamples(res.data.samples)
      setCachedAt(null)
      setLoadError(false)
      putCachedSamples(res.data.samples)
      // This 6s poll succeeding is proof of connectivity -- the natural,
      // already-recurring trigger to flush anything queued while offline.
      runSyncPass().catch(() => { /* best-effort; failures just leave items queued */ })
    } catch (err) {
      if (!isNetworkError(err)) throw err
      const cached = await getCachedSamples()
      if (cached) {
        setSamples(cached.data)
        setCachedAt(cached.cachedAt)
        setLoadError(false)
      } else {
        setLoadError(true)
      }
    }
  }, [])

  useEffect(() => {
    load()
    const id = setInterval(load, 6000)
    return () => clearInterval(id)
  }, [load])

  if (loadError) {
    return (
      <Center h={300}>
        <Text c="dimmed" size="sm" ta="center" px="xl">
          Can't reach the server, and no samples are cached on this device yet.
          Connect once to load your samples, then this works offline.
        </Text>
      </Center>
    )
  }

  if (!samples) return <Center h={300}><Loader /></Center>

  const active = samples.filter((s) => !['ARCHIVED', 'APPROVED', 'REPORT_GENERATED'].includes(s.status))
  const done = samples.filter((s) => ['ARCHIVED', 'APPROVED', 'REPORT_GENERATED'].includes(s.status))

  return (
    <Box px="md" py="md">
      <Title order={3} mb={4}>My Samples</Title>
      <Text c="dimmed" size="sm" mb="md">Tap a sample to capture the profile or enter test readings</Text>
      {cachedAt != null && <Box mb="md"><OfflineBanner cachedAt={cachedAt} /></Box>}

      <Stack gap="xs">
        {active.map((s) => (
          <Card key={s.sample_id} withBorder radius="md" p="md" onClick={() => navigate(`/assistant/samples/${s.sample_id}`)} style={{ cursor: 'pointer' }}>
            <Group justify="space-between">
              <Group gap="sm">
                <IconPlugConnected size={22} color="#19376D" />
                <Stack gap={0}>
                  <Text fw={700}>{s.sample_id}</Text>
                  <Text size="xs" c="dimmed">{s.standard} &middot; {s.cores}C &middot; {s.csa_mm2}mm²</Text>
                </Stack>
              </Group>
              <Group gap={6}>
                {s.last_review_comment && (
                  <Tooltip label={s.last_review_comment} multiline w={260} withArrow>
                    <IconArrowBack size={16} color="#E8590C" />
                  </Tooltip>
                )}
                <StatusBadge status={s.status} size="sm" />
                <IconChevronRight size={16} color="gray" />
              </Group>
            </Group>
            {s.summary.applicable_tests > 0 && (
              <Text size="xs" c="dimmed" mt={6}>
                {s.summary.completed_tests}/{s.summary.applicable_tests} tests completed
              </Text>
            )}
          </Card>
        ))}
        {active.length === 0 && (
          <Card withBorder radius="md" p="lg"><Text c="dimmed" ta="center" size="sm">No active samples assigned.</Text></Card>
        )}
      </Stack>

      {done.length > 0 && (
        <>
          <Text fw={700} size="sm" c="dimmed" mt="xl" mb="xs">Completed</Text>
          <Stack gap="xs">
            {done.map((s) => (
              <Card key={s.sample_id} withBorder radius="md" p="sm" opacity={0.7} onClick={() => navigate(`/assistant/samples/${s.sample_id}`)} style={{ cursor: 'pointer' }}>
                <Group justify="space-between">
                  <Text size="sm" fw={600}>{s.sample_id}</Text>
                  <StatusBadge status={s.status} size="sm" />
                </Group>
              </Card>
            ))}
          </Stack>
        </>
      )}
    </Box>
  )
}
