import { useState } from 'react'
import {
  ActionIcon, Indicator, Drawer, Stack, Text, Group, Badge, Button, Loader, Divider, Center, Box,
} from '@mantine/core'
import { IconCloudUpload, IconRefresh, IconTrash, IconCheck } from '@tabler/icons-react'
import { useOutboxSummary } from './useOutboxSummary'
import { markPending, discard, type OutboxItem } from './outbox'
import { runSyncPass } from './syncEngine'

const KIND_LABELS: Record<OutboxItem['kind'], string> = {
  PROFILE: 'Cable Profile', MARKING_IMAGE: 'Marking Photo', DIAGRAM_IMAGE: 'Diagram', TEST_SUBMIT: 'Test Reading',
}

function ItemRow({ item, onChanged }: { item: OutboxItem; onChanged: () => void }) {
  const [busy, setBusy] = useState(false)

  async function retryNow() {
    setBusy(true)
    try {
      await markPending(item)
      await runSyncPass()
    } finally {
      setBusy(false)
      onChanged()
    }
  }

  async function discardItem() {
    setBusy(true)
    try {
      await discard(item)
    } finally {
      setBusy(false)
      onChanged()
    }
  }

  return (
    <Stack gap={4} py={6}>
      <Group justify="space-between">
        <Text size="sm" fw={600}>{KIND_LABELS[item.kind]}</Text>
        {item.status === 'pending' && <Badge size="sm" color="blue" variant="light">Waiting to sync</Badge>}
        {item.status === 'syncing' && <Badge size="sm" color="blue" variant="light" leftSection={<Loader size={10} />}>Syncing</Badge>}
        {item.status === 'failed' && item.errorKind === 'transient' && (
          <Badge size="sm" color="orange" variant="light">No connection yet</Badge>
        )}
        {item.status === 'failed' && item.errorKind === 'rejected' && (
          <Badge size="sm" color="red" variant="light">Rejected</Badge>
        )}
      </Group>
      <Text size="xs" c="dimmed">Sample {item.sampleId}</Text>
      {item.status === 'failed' && item.errorKind === 'rejected' && item.lastError && (
        <Text size="xs" c="red">{item.lastError}</Text>
      )}
      {item.status === 'failed' && item.errorKind === 'transient' && (
        <Button size="compact-xs" variant="light" color="orange" leftSection={<IconRefresh size={12} />}
                loading={busy} onClick={retryNow} w="fit-content">
          Retry now
        </Button>
      )}
      {item.status === 'failed' && item.errorKind === 'rejected' && (
        <Button size="compact-xs" variant="light" color="red" leftSection={<IconTrash size={12} />}
                loading={busy} onClick={discardItem} w="fit-content">
          Discard -- I'll redo this
        </Button>
      )}
    </Stack>
  )
}

export function SyncStatusBadge() {
  const [opened, setOpened] = useState(false)
  const { items, refresh } = useOutboxSummary()

  const pendingCount = items.length

  return (
    <>
      <Indicator label={pendingCount} size={16} disabled={pendingCount === 0} color="orange" offset={4}>
        <ActionIcon variant="subtle" color="white" onClick={() => setOpened(true)}>
          <IconCloudUpload size={20} />
        </ActionIcon>
      </Indicator>

      <Drawer opened={opened} onClose={() => setOpened(false)} position="right" title="Sync Status" size="sm">
        {items.length === 0 ? (
          <Center py="xl">
            <Stack align="center" gap={4}>
              <IconCheck size={28} color="#2f9e44" />
              <Text size="sm" c="dimmed">Everything is synced.</Text>
            </Stack>
          </Center>
        ) : (
          <Stack gap={0}>
            {items.map((item, i) => (
              <Box key={item.id}>
                {i > 0 && <Divider />}
                <ItemRow item={item} onChanged={refresh} />
              </Box>
            ))}
          </Stack>
        )}
      </Drawer>
    </>
  )
}
