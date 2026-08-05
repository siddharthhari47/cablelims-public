import { useEffect, useState, useCallback, useRef } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import {
  Box, Stack, Text, Title, Card, Group, Loader, Center,
  ActionIcon, Alert, Progress, Accordion,
} from '@mantine/core'
import {
  IconArrowLeft, IconArrowBack, IconCamera, IconInfoCircle, IconLock,
} from '@tabler/icons-react'
import { api } from '../../api/client'
import { TestEntryCard, CorePositionBadge } from '../../components/TestEntryCard'
import { ConstructionProfileForm } from '../../components/ConstructionProfileForm'
import { ProfileSummaryCard } from '../../components/ProfileSummaryCard'
import { getCachedSampleDetail, putCachedSampleDetail } from '../../offline/db'
import { OfflineBanner } from '../../offline/OfflineBanner'
import { isNetworkError } from '../../offline/isNetworkError'
import { queueOrSend } from '../../offline/queueOrSend'
import { sendMarkingImage } from '../../offline/sends'
import { runSyncPass } from '../../offline/syncEngine'
import { compressImage } from '../../offline/compressImage'
import type { SampleDetail } from '../../types'

function ProfileForm({ sample, onSaved }: { sample: SampleDetail; onSaved: () => void }) {
  const [imageUploaded, setImageUploaded] = useState(false)
  const [imageQueued, setImageQueued] = useState(false)
  const [ocrNote, setOcrNote] = useState<string | null>(null)
  const fileRef = useRef<HTMLInputElement>(null)

  async function handleFile(e: React.ChangeEvent<HTMLInputElement>) {
    const rawFile = e.target.files?.[0]
    if (!rawFile) return
    const file = await compressImage(rawFile)
    const result = await queueOrSend(
      () => sendMarkingImage(sample.sample_id, file, file.name),
      () => ({ id: crypto.randomUUID(), sampleId: sample.sample_id, kind: 'MARKING_IMAGE', payload: { blob: file, filename: file.name } }),
    )
    setImageUploaded(true)
    if (result.status === 'sent') {
      setOcrNote(result.data.data.note)
    } else {
      setImageQueued(true)
    }
  }

  return (
    <Stack gap="md" px="md" py="md">
      <Text fw={700}>Stage 1 &middot; Observation: Cable Marking</Text>
      <Card withBorder radius="md" p="md" onClick={() => fileRef.current?.click()} style={{ cursor: 'pointer', borderStyle: 'dashed' }}>
        <input ref={fileRef} type="file" accept="image/*" capture="environment" hidden onChange={handleFile} />
        <Group justify="center" gap="xs" py="sm">
          <IconCamera size={22} color="#19376D" />
          <Text size="sm" c={imageUploaded ? 'green' : 'dimmed'}>{imageUploaded ? 'Marking photo uploaded' : 'Tap to photograph cable marking'}</Text>
        </Group>
      </Card>
      {imageQueued && (
        <Alert color="blue" icon={<IconInfoCircle size={16} />} variant="light">Saved offline -- will upload once back online.</Alert>
      )}
      {ocrNote && (
        <Alert color="yellow" icon={<IconInfoCircle size={16} />} variant="light">{ocrNote}</Alert>
      )}

      <ConstructionProfileForm
        sampleId={sample.sample_id}
        coresTested={sample.cores_tested ?? sample.cores}
        suggestedCoreColors={sample.suggested_core_colors}
        onSaved={onSaved}
        offlineQueue
      />
    </Stack>
  )
}

const POSITION_LABELS: Record<string, string> = {
  WHOLE: 'Whole Sample', RED: 'Red Core', YELLOW: 'Yellow Core', BLUE: 'Blue Core', BLACK: 'Black Core', SHEATH: 'Outer Sheath',
}

export default function AssistantSamplePage() {
  const { sampleId } = useParams()
  const navigate = useNavigate()
  const [sample, setSample] = useState<SampleDetail | null>(null)
  const [cachedAt, setCachedAt] = useState<number | null>(null)
  const [loadError, setLoadError] = useState(false)

  const load = useCallback(async () => {
    if (!sampleId) return
    try {
      const res = await api.get(`/samples/${sampleId}`)
      setSample(res.data)
      setCachedAt(null)
      setLoadError(false)
      putCachedSampleDetail(res.data)
      // A successful fetch is proof of connectivity -- a natural trigger to
      // flush anything queued while this device was offline.
      runSyncPass().catch(() => { /* best-effort; failures just leave items queued */ })
    } catch (err) {
      if (!isNetworkError(err)) throw err
      const cached = await getCachedSampleDetail(sampleId)
      if (cached) {
        setSample(cached.data)
        setCachedAt(cached.cachedAt)
        setLoadError(false)
      } else {
        setLoadError(true)
      }
    }
  }, [sampleId])

  useEffect(() => { load() }, [load])

  if (loadError) {
    return (
      <Center h={300}>
        <Text c="dimmed" size="sm" ta="center" px="xl">
          Can't reach the server, and this sample isn't cached on this device yet.
          Open it once while connected to work on it offline.
        </Text>
      </Center>
    )
  }

  if (!sample) return <Center h={300}><Loader /></Center>

  const showProfileForm = !sample.profile?.confirmed
  const s = sample.summary

  // group tests by core/sheath position for the Observation stage --
  // Sprint Priority 1 (per-core generation) + Priority 9 (clear stages)
  const groups: Record<string, typeof sample.tests> = {}
  for (const t of sample.tests) {
    const key = t.core_position ?? 'WHOLE'
    groups[key] = groups[key] ?? []
    groups[key].push(t)
  }
  const groupOrder = ['WHOLE', 'RED', 'YELLOW', 'BLUE', 'BLACK', 'SHEATH'].filter((k) => groups[k]?.length)

  return (
    <Box>
      <Group px="md" pt="md" gap="xs">
        <ActionIcon variant="subtle" onClick={() => navigate('/assistant')}><IconArrowLeft size={18} /></ActionIcon>
        <Stack gap={0}>
          <Title order={4}>{sample.sample_id}</Title>
          <Text size="xs" c="dimmed">
            {sample.standard?.name} &middot; {sample.cores} core{sample.cores_tested !== sample.cores ? ` (${sample.cores_tested} tested)` : ''} &middot; {sample.csa_mm2} mm²
          </Text>
        </Stack>
      </Group>

      {cachedAt != null && (
        <Box m="md"><OfflineBanner cachedAt={cachedAt} /></Box>
      )}

      {sample.locked && (
        <Alert color="gray" icon={<IconLock size={16} />} m="md">
          This sample is {sample.status.replace('_', ' ').toLowerCase()} and locked. No further edits are possible here.
        </Alert>
      )}

      {sample.last_review_comment && (
        <Alert color="orange" icon={<IconArrowBack size={16} />} title="Returned by the Scientist" m="md">
          {sample.last_review_comment}
        </Alert>
      )}

      {!showProfileForm && s.applicable_tests > 0 && (
        <Box px="md" mt="sm">
          <Group justify="space-between" mb={4}>
            <Text size="xs" c="dimmed">Stage 1 &middot; Observation progress</Text>
            <Text size="xs" c="dimmed">{s.completed_tests}/{s.applicable_tests}</Text>
          </Group>
          <Progress value={(s.completed_tests / Math.max(s.applicable_tests, 1)) * 100} radius="xl" />
        </Box>
      )}

      {showProfileForm ? (
        <ProfileForm sample={sample} onSaved={load} />
      ) : sample.locked ? (
        <Stack gap="sm" px="md" py="md">
          {sample.profile && <ProfileSummaryCard profile={sample.profile} coresTested={sample.cores_tested ?? sample.cores} sampleId={sample.sample_id} />}
          {sample.tests.map((t) => (
            <TestEntryCard key={t.assigned_test_id} sampleId={sample.sample_id} test={t} allTests={sample.tests} onSubmitted={load} offlineQueue />
          ))}
        </Stack>
      ) : (
        <Box px="md" py="md">
          {sample.profile && (
            <Box mb="md">
              <ProfileSummaryCard profile={sample.profile} coresTested={sample.cores_tested ?? sample.cores} />
            </Box>
          )}
          <Text fw={700} mb="sm">Stage 1 &middot; Observation: Raw Readings</Text>
          <Accordion multiple defaultValue={groupOrder}>
            {groupOrder.map((key) => (
              <Accordion.Item key={key} value={key}>
                <Accordion.Control>
                  <Group gap={8}>
                    {key !== 'WHOLE' ? <CorePositionBadge position={key} /> : null}
                    <Text size="sm" fw={600}>{POSITION_LABELS[key]}</Text>
                    <Text size="xs" c="dimmed">
                      {groups[key].filter((t) => t.status === 'COMPLETED').length}/{groups[key].length} done
                    </Text>
                  </Group>
                </Accordion.Control>
                <Accordion.Panel>
                  <Stack gap="sm">
                    {groups[key].map((t) => (
                      <TestEntryCard key={t.assigned_test_id} sampleId={sample.sample_id} test={t} allTests={sample.tests} onSubmitted={load} offlineQueue />
                    ))}
                  </Stack>
                </Accordion.Panel>
              </Accordion.Item>
            ))}
          </Accordion>
          {sample.tests.length === 0 && <Text c="dimmed" size="sm" ta="center">No tests assigned yet.</Text>}
          {sample.status === 'SCIENTIST_REVIEW' && (
            <Alert color="grape" icon={<IconInfoCircle size={16} />} mt="md">
              All tests submitted. This sample is now with the Scientist for review.
            </Alert>
          )}
        </Box>
      )}
    </Box>
  )
}
