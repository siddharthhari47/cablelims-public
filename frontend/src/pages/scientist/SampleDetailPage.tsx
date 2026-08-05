import { useEffect, useState, useCallback } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import {
  Box, Stack, Group, Text, Title, Paper, Button, Loader, Center,
  Breadcrumbs, Anchor, Divider, Tabs, Alert, Accordion, Modal, Textarea,
} from '@mantine/core'
import { notifications } from '@mantine/notifications'
import {
  IconCheck, IconArrowBack, IconFileCertificate, IconDownload, IconInfoCircle,
  IconClipboardList, IconCalculator, IconFileCheck, IconLock,
} from '@tabler/icons-react'
import { api, extractErrorMessage } from '../../api/client'
import { SystemDecisionPanel } from '../../components/SystemDecisionPanel'
import { StatusBadge } from '../../components/StatusBadge'
import { TestEntryCard, CorePositionBadge } from '../../components/TestEntryCard'
import { ConstructionProfileForm } from '../../components/ConstructionProfileForm'
import { ProfileSummaryCard } from '../../components/ProfileSummaryCard'
import { CalculationMatrix } from '../../components/CalculationMatrix'
import type { SampleDetail } from '../../types'

const POSITION_LABELS: Record<string, string> = {
  WHOLE: 'Whole Sample', RED: 'Red Core', YELLOW: 'Yellow Core', BLUE: 'Blue Core', BLACK: 'Black Core', SHEATH: 'Outer Sheath',
}

export default function SampleDetailPage() {
  const { sampleId } = useParams()
  const navigate = useNavigate()
  const [sample, setSample] = useState<SampleDetail | null>(null)
  const [busy, setBusy] = useState(false)
  const [returnModalOpen, setReturnModalOpen] = useState(false)
  const [returnComment, setReturnComment] = useState('')

  const load = useCallback(async () => {
    const res = await api.get(`/samples/${sampleId}`)
    setSample(res.data)
  }, [sampleId])

  useEffect(() => {
    load()
    const id = setInterval(load, 5000)
    return () => clearInterval(id)
  }, [load])

  async function toggleTest(assignedTestId: string, enabled: boolean) {
    await api.post(`/samples/${sampleId}/tests/${assignedTestId}/toggle`, null, { params: { enabled } })
    load()
  }

  async function requestRepeat(assignedTestId: string) {
    setBusy(true)
    try {
      await api.post(`/samples/${sampleId}/tests/${assignedTestId}/repeat`)
      notifications.show({ title: 'Repeat requested', message: 'Assigned back for a new attempt', color: 'orange' })
      load()
    } finally {
      setBusy(false)
    }
  }

  async function overrideResult(assignedTestId: string, body: { result: string; limit_value: number | null; reason: string }) {
    setBusy(true)
    try {
      await api.post(`/samples/${sampleId}/tests/${assignedTestId}/override`, body)
      notifications.show({ title: 'Result overridden', message: `Recorded as ${body.result}`, color: 'grape' })
      load()
    } catch (err: unknown) {
      notifications.show({ title: 'Could not override result', message: extractErrorMessage(err), color: 'red' })
    } finally {
      setBusy(false)
    }
  }

  async function review(action: 'APPROVE' | 'RETURN', comment?: string) {
    setBusy(true)
    try {
      await api.post(`/samples/${sampleId}/review`, { action, comment })
      notifications.show({
        title: action === 'APPROVE' ? 'Sample approved' : 'Sample returned',
        message: action === 'APPROVE' ? 'Ready for certificate generation' : 'Sent back for further testing',
        color: action === 'APPROVE' ? 'green' : 'orange',
      })
      if (action === 'RETURN') {
        setReturnModalOpen(false)
        setReturnComment('')
      }
      load()
    } catch (err: unknown) {
      notifications.show({ title: 'Could not return sample', message: extractErrorMessage(err), color: 'red' })
    } finally {
      setBusy(false)
    }
  }

  // A plain <a href> to these endpoints won't carry the Bearer token (only
  // axios calls get it, via the request interceptor in api/client.ts) --
  // the API rejects it as unauthenticated. Fetch through the same
  // authenticated client instead and save the blob manually.
  async function downloadFile(url: string, fallbackFilename: string, errorTitle: string) {
    try {
      const res = await api.get(url, { responseType: 'blob' })
      // Server names the file (and picks the extension) via
      // Content-Disposition; fall back only if that's ever missing.
      const disposition = res.headers['content-disposition'] as string | undefined
      const match = disposition?.match(/filename="?([^"]+)"?/)
      const filename = match?.[1] ?? fallbackFilename
      const contentType = String(res.headers['content-type'] ?? 'application/octet-stream')
      const blobUrl = URL.createObjectURL(new Blob([res.data], { type: contentType }))
      const link = document.createElement('a')
      link.href = blobUrl
      link.download = filename
      document.body.appendChild(link)
      link.click()
      link.remove()
      URL.revokeObjectURL(blobUrl)
    } catch (err: unknown) {
      notifications.show({ title: errorTitle, message: extractErrorMessage(err), color: 'red' })
    }
  }

  function downloadCertificate(certificateNo: string) {
    return downloadFile(
      `/certificates/${encodeURIComponent(certificateNo)}/download`,
      `${certificateNo.replace(/\//g, '_')}.docx`, 'Could not download certificate',
    )
  }

  function downloadObservationSheet() {
    return downloadFile(
      `/samples/${sampleId}/observation-sheet`,
      `${sampleId}_ObservationSheet.docx`, 'Could not download Observation Sheet',
    )
  }

  async function generateCertificate() {
    setBusy(true)
    try {
      const res = await api.post(`/samples/${sampleId}/certificate`)
      notifications.show({
        title: 'Certificate generated', message: res.data.certificate_no, color: 'green',
        icon: <IconFileCertificate size={16} />,
      })
      load()
    } catch {
      notifications.show({ title: 'Error', message: 'Could not generate certificate', color: 'red' })
    } finally {
      setBusy(false)
    }
  }

  if (!sample) return <Center h={300}><Loader /></Center>

  const canReview = sample.status === 'SCIENTIST_REVIEW'
  const canCertify = sample.status === 'APPROVED'
  const canObserve = !sample.locked && sample.profile?.confirmed && sample.tests.length > 0

  const groups: Record<string, typeof sample.tests> = {}
  for (const t of sample.tests) {
    const key = t.core_position ?? 'WHOLE'
    groups[key] = groups[key] ?? []
    groups[key].push(t)
  }
  const groupOrder = ['WHOLE', 'RED', 'YELLOW', 'BLUE', 'BLACK', 'SHEATH'].filter((k) => groups[k]?.length)

  return (
    <Stack gap="md">
      <Breadcrumbs>
        <Anchor onClick={() => navigate('/dashboard')} size="sm">Dashboard</Anchor>
        <Text size="sm">{sample.sample_id}</Text>
      </Breadcrumbs>

      <Group justify="space-between" align="flex-start">
        <Stack gap={0}>
          <Title order={2}>{sample.sample_id}</Title>
          <Text c="dimmed" size="sm">
            Registered by {sample.registered_by?.full_name} &middot; Assigned to {sample.assigned_assistant?.full_name ?? 'unassigned'}
            {sample.cores_tested !== sample.cores && ` · ${sample.cores_tested} of ${sample.cores} cores tested`}
          </Text>
        </Stack>
        <Group>
          {canReview && (
            <>
              <Button variant="default" color="orange" leftSection={<IconArrowBack size={16} />} onClick={() => setReturnModalOpen(true)} loading={busy}>
                Return for Testing
              </Button>
              <Button color="green" leftSection={<IconCheck size={16} />} onClick={() => review('APPROVE')} loading={busy}>
                Approve
              </Button>
            </>
          )}
          {canCertify && (
            <Button leftSection={<IconFileCertificate size={16} />} onClick={generateCertificate} loading={busy}>
              Generate Certificate
            </Button>
          )}
          {sample.certificate && (
            <Button
              variant="light" color="teal" leftSection={<IconDownload size={16} />}
              onClick={() => downloadCertificate(sample.certificate!.certificate_no)}
            >
              Download Certificate
            </Button>
          )}
          {sample.profile?.confirmed && (
            <Button
              variant="light" color="grape" leftSection={<IconDownload size={16} />}
              onClick={downloadObservationSheet}
            >
              Download Observation Sheet
            </Button>
          )}
        </Group>
      </Group>

      {sample.locked && (
        <Alert color="gray" icon={<IconLock size={16} />}>
          This sample is {sample.status.replace(/_/g, ' ').toLowerCase()} and locked. Its profile and readings can no
          longer be edited directly -- any correction now needs a documented revision.
        </Alert>
      )}

      {sample.last_review_comment && (
        <Alert color="orange" icon={<IconArrowBack size={16} />} title="Returned for correction">
          {sample.last_review_comment}
        </Alert>
      )}

      <SystemDecisionPanel sample={sample} />

      <Tabs defaultValue="observation" keepMounted={false}>
        <Tabs.List>
          <Tabs.Tab value="observation" leftSection={<IconClipboardList size={16} />}>1. Observation</Tabs.Tab>
          <Tabs.Tab value="calculation" leftSection={<IconCalculator size={16} />}>2. Calculation</Tabs.Tab>
          <Tabs.Tab value="report" leftSection={<IconFileCheck size={16} />}>3. Report</Tabs.Tab>
        </Tabs.List>

        <Tabs.Panel value="observation" pt="md">
          {!sample.locked && !sample.profile?.confirmed && (
            <Paper p="md" radius="lg" withBorder mb="md">
              <Text size="xs" c="dimmed" mb="sm">
                A Scientist may enter the cable profile directly, or leave this to the assigned Scientific Assistant.
              </Text>
              <ConstructionProfileForm
                sampleId={sample.sample_id}
                coresTested={sample.cores_tested ?? sample.cores}
                suggestedCoreColors={sample.suggested_core_colors}
                onSaved={load}
              />
            </Paper>
          )}
          {sample.profile?.confirmed && (
            <Box mb="md">
              <ProfileSummaryCard profile={sample.profile} coresTested={sample.cores_tested ?? sample.cores} />
            </Box>
          )}
          <Paper p="md" radius="lg" withBorder>
            <Group justify="space-between" mb="sm">
              <Text fw={700}>Raw Readings</Text>
              <Text size="xs" c="dimmed">
                A Scientist may enter observations directly, or leave this to the assigned Scientific Assistant.
              </Text>
            </Group>
            {!canObserve && (
              <Text size="sm" c="dimmed">
                {sample.locked ? 'This sample is locked.' : 'Profile not confirmed / no tests assigned yet.'}
              </Text>
            )}
            {canObserve && (
              <Accordion multiple defaultValue={[]}>
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
                          <TestEntryCard key={t.assigned_test_id} sampleId={sample.sample_id} test={t} allTests={sample.tests} onSubmitted={load} />
                        ))}
                      </Stack>
                    </Accordion.Panel>
                  </Accordion.Item>
                ))}
              </Accordion>
            )}
          </Paper>
        </Tabs.Panel>

        <Tabs.Panel value="calculation" pt="md">
          <Paper p="md" radius="lg" withBorder>
            <Group justify="space-between" mb="md">
              <Text fw={700}>Calculated Results</Text>
              <Text size="xs" c="dimmed">{sample.tests.length} tests assigned</Text>
            </Group>
            <CalculationMatrix
              tests={sample.tests} locked={sample.locked}
              onToggle={toggleTest} onRepeat={requestRepeat} onOverride={overrideResult} busy={busy}
            />
            <Divider my="md" />
            <Group gap={6}>
              <IconInfoCircle size={14} color="gray" />
              <Text size="xs" c="dimmed">
                Placeholder and missing-criterion results are never auto-decided &mdash; they route to Scientist review by design.
                Tap the <IconInfoCircle size={12} style={{ verticalAlign: 'middle' }} /> next to a test name to see its calculation procedure.
              </Text>
            </Group>
          </Paper>
        </Tabs.Panel>

        <Tabs.Panel value="report" pt="md">
          <Paper p="md" radius="lg" withBorder>
            <Text fw={700} mb="sm">Review &amp; Certificate</Text>
            <Stack gap="sm">
              <Group gap="xs">
                <Text size="sm" c="dimmed">Status:</Text>
                <StatusBadge status={sample.status} />
              </Group>
              {sample.summary.repeat_required.length > 0 && (
                <Alert color="orange" icon={<IconInfoCircle size={16} />}>
                  Needs attention before approval: {sample.summary.repeat_required.join(', ')}
                </Alert>
              )}
              {!canReview && !canCertify && !sample.certificate && (
                <Text size="sm" c="dimmed">Nothing to review yet -- complete Stage 1 observations first.</Text>
              )}
              {canReview && (
                <Group>
                  <Button variant="default" color="orange" leftSection={<IconArrowBack size={16} />} onClick={() => setReturnModalOpen(true)} loading={busy}>
                    Return for Testing
                  </Button>
                  <Button color="green" leftSection={<IconCheck size={16} />} onClick={() => review('APPROVE')} loading={busy}>
                    Approve
                  </Button>
                </Group>
              )}
              {canCertify && (
                <Button leftSection={<IconFileCertificate size={16} />} onClick={generateCertificate} loading={busy} style={{ width: 'fit-content' }}>
                  Generate Certificate
                </Button>
              )}
              {sample.certificate && (
                <Stack gap={4}>
                  <Text size="sm">Certificate <b>{sample.certificate.certificate_no}</b> &mdash; {sample.certificate.overall_decision.replace(/_/g, ' ')}</Text>
                  <Button
                    variant="light" color="teal" leftSection={<IconDownload size={16} />}
                    onClick={() => downloadCertificate(sample.certificate!.certificate_no)}
                    style={{ width: 'fit-content' }}
                  >
                    Download Certificate
                  </Button>
                </Stack>
              )}
              {sample.profile?.confirmed && (
                <Button
                  variant="light" color="grape" leftSection={<IconDownload size={16} />}
                  onClick={downloadObservationSheet} style={{ width: 'fit-content' }}
                >
                  Download Observation Sheet
                </Button>
              )}
            </Stack>
          </Paper>
        </Tabs.Panel>
      </Tabs>

      <Modal
        opened={returnModalOpen} onClose={() => setReturnModalOpen(false)}
        title={<Title order={4}>Return for Testing</Title>} size="md" centered
      >
        <Stack gap="md">
          <Text size="sm" c="dimmed">
            This sample goes back to the assigned Scientific Assistant. Explain what needs correcting -- they'll
            see this comment on the sample.
          </Text>
          <Textarea
            label="Comment (required)" required minRows={3} autoFocus
            placeholder="What needs to be corrected before this can be reviewed again?"
            value={returnComment} onChange={(e) => setReturnComment(e.currentTarget.value)}
          />
          <Group justify="flex-end">
            <Button variant="default" onClick={() => setReturnModalOpen(false)}>Cancel</Button>
            <Button
              color="orange" loading={busy} disabled={!returnComment.trim()}
              onClick={() => review('RETURN', returnComment)}
            >
              Return Sample
            </Button>
          </Group>
        </Stack>
      </Modal>
    </Stack>
  )
}
