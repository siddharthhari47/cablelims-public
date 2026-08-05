import { Paper, Group, Stack, Text, Divider, RingProgress, Center, Badge, SimpleGrid } from '@mantine/core'
import { IconCpu } from '@tabler/icons-react'
import { StatusBadge } from './StatusBadge'
import type { SampleDetail } from '../types'

export function SystemDecisionPanel({ sample }: { sample: SampleDetail }) {
  const s = sample.summary
  const confidence = s.overall_confidence_pct ?? 0
  const confColor = confidence >= 90 ? 'green' : confidence >= 70 ? 'yellow' : 'red'

  return (
    <Paper
      radius="lg" p="lg" withBorder
      style={{
        background: 'linear-gradient(135deg, #0B2447 0%, #19376D 100%)',
        color: 'white',
      }}
    >
      <Group justify="space-between" mb="md">
        <Group gap="xs">
          <IconCpu size={20} />
          <Text fw={700} tt="uppercase" size="sm" style={{ letterSpacing: 1 }}>System Decision</Text>
        </Group>
        <StatusBadge status={s.overall_status} />
      </Group>

      <SimpleGrid cols={{ base: 1, sm: 2, md: 4 }} spacing="lg">
        <Stack gap={2}>
          <Text size="xs" c="gray.4">Sample</Text>
          <Text fw={700} size="lg">{sample.sample_id}</Text>
          <Text size="xs" c="gray.4">{sample.standard?.name} : {sample.standard?.edition}</Text>
        </Stack>

        <Stack gap={2}>
          <Text size="xs" c="gray.4">Detected Profile</Text>
          <Group gap={6}>
            <Badge variant="white" color="dark" size="sm">{sample.profile?.conductor_material ?? '—'}</Badge>
            <Badge variant="white" color="dark" size="sm">{sample.cores} Core</Badge>
            <Badge variant="white" color="dark" size="sm">{sample.csa_mm2} sq.mm</Badge>
          </Group>
          <Badge variant="white" color="dark" size="sm" mt={4} style={{ width: 'fit-content' }}>
            {sample.profile?.fire_category ?? '—'}
          </Badge>
        </Stack>

        <Stack gap={2}>
          <Text size="xs" c="gray.4">Applicable Tests</Text>
          <Text fw={700} size="lg">{s.applicable_tests}</Text>
          <Text size="xs" c="gray.4">
            Completed {s.completed_tests} &middot; Passed {s.passed}
            {s.failed > 0 && <> &middot; Failed {s.failed}</>}
          </Text>
        </Stack>

        <Group gap="md" wrap="nowrap">
          <RingProgress
            size={70} thickness={7}
            sections={[{ value: confidence, color: confColor }]}
            label={<Center><Text size="xs" fw={700}>{confidence ? `${confidence}%` : '—'}</Text></Center>}
          />
          <Stack gap={2}>
            <Text size="xs" c="gray.4">Confidence</Text>
            <Text size="xs" c="gray.4">System-computed</Text>
          </Stack>
        </Group>
      </SimpleGrid>

      {s.repeat_required.length > 0 && (
        <>
          <Divider my="sm" color="gray.7" />
          <Group gap={6}>
            <Text size="xs" c="orange.3" fw={600}>Requires Scientist Review:</Text>
            {s.repeat_required.map((name) => (
              <Badge key={name} color="orange" variant="light" size="sm">{name}</Badge>
            ))}
          </Group>
        </>
      )}
    </Paper>
  )
}
