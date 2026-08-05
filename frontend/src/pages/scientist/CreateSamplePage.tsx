import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Title, Text, Paper, Stack, Select, NumberInput, Textarea, Button, Group, Breadcrumbs, Anchor, Alert,
} from '@mantine/core'
import { notifications } from '@mantine/notifications'
import { IconCheck, IconInfoCircle } from '@tabler/icons-react'
import { api, extractErrorMessage } from '../../api/client'
import type { Standard } from '../../types'

interface Assistant { id: string; full_name: string; username: string }

const MAX_NAMED_CORE_COLORS = 4

export default function CreateSamplePage() {
  const navigate = useNavigate()
  const [standards, setStandards] = useState<Standard[]>([])
  const [assistants, setAssistants] = useState<Assistant[]>([])
  const [standardId, setStandardId] = useState<string | null>(null)
  const [cores, setCores] = useState<number | ''>(3)
  const [coresTested, setCoresTested] = useState<number | ''>(4)
  const [csa, setCsa] = useState<number | ''>(2.5)
  const [remarks, setRemarks] = useState('')
  const [assistantId, setAssistantId] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  useEffect(() => {
    api.get('/meta/standards').then((r) => setStandards(r.data))
    api.get('/meta/assistants').then((r) => setAssistants(r.data))
  }, [])

  const needsCoreCountPrompt = typeof cores === 'number' && cores > MAX_NAMED_CORE_COLORS
  const effectiveCoresTested = needsCoreCountPrompt ? coresTested : cores

  async function submit() {
    if (!standardId || !cores || !csa) return
    if (needsCoreCountPrompt && !coresTested) return
    setSubmitting(true)
    try {
      const res = await api.post('/samples', {
        standard_id: standardId, cores, csa_mm2: csa, remarks, assigned_assistant_id: assistantId,
        cores_tested: needsCoreCountPrompt ? coresTested : undefined,
      })
      notifications.show({
        title: 'Sample registered', message: `${res.data.sample_id} created successfully`,
        color: 'green', icon: <IconCheck size={16} />,
      })
      navigate(`/samples/${res.data.sample_id}`)
    } catch (err: unknown) {
      notifications.show({ title: 'Could not create sample', message: extractErrorMessage(err), color: 'red' })
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <Stack gap="md" maw={640}>
      <Breadcrumbs>
        <Anchor onClick={() => navigate('/dashboard')} size="sm">Dashboard</Anchor>
        <Text size="sm">Register Sample</Text>
      </Breadcrumbs>
      <Title order={2}>Register New Sample</Title>
      <Text c="dimmed" size="sm">
        Enter the minimum information required to begin testing. The Scientific Assistant will capture the
        detailed cable profile from the marking on their device.
      </Text>

      <Paper p="lg" radius="lg" withBorder>
        <Stack gap="md">
          <Select
            label="Applicable Standard" placeholder="Select standard" required
            data={standards.map((s) => ({ value: s.standard_id, label: `${s.name}${s.edition ? ' : ' + s.edition : ''}` }))}
            value={standardId} onChange={setStandardId}
            description={standards.find((s) => s.standard_id === standardId)?.scope_summary}
          />
          <Group grow align="flex-start">
            <NumberInput label="Number of Cores" value={cores} onChange={(v) => setCores(v as number)} min={1} max={100} required />
            <NumberInput
              label="Nominal Cross Sectional Area (mm²)" value={csa} onChange={(v) => setCsa(v as number)}
              min={0.5} step={0.5} decimalScale={2} required
            />
          </Group>

          {needsCoreCountPrompt ? (
            <Alert color="blue" icon={<IconInfoCircle size={16} />} variant="light">
              <Stack gap="xs">
                <Text size="sm">
                  This cable has {cores} cores &mdash; more than the {MAX_NAMED_CORE_COLORS} that can be tested with a
                  named colour. How many cores are required for testing?
                </Text>
                <NumberInput
                  label="Cores required for testing" value={coresTested}
                  onChange={(v) => setCoresTested(v as number)} min={1} max={MAX_NAMED_CORE_COLORS} required
                  w={220}
                />
              </Stack>
            </Alert>
          ) : (
            <Text size="xs" c="dimmed">
              {typeof effectiveCoresTested === 'number' && effectiveCoresTested > 0 &&
                `Every core will be tested. Colours are assigned explicitly during profiling, not automatically.`}
            </Text>
          )}

          <Select
            label="Scientific Assistant Assigned" placeholder="Select assistant"
            data={assistants.map((a) => ({ value: a.id, label: a.full_name }))}
            value={assistantId} onChange={setAssistantId}
          />
          <Textarea label="Remarks" placeholder="Optional notes for this sample" value={remarks} onChange={(e) => setRemarks(e.currentTarget.value)} minRows={2} />

          <Group justify="flex-end" mt="sm">
            <Button variant="default" onClick={() => navigate('/dashboard')}>Cancel</Button>
            <Button onClick={submit} loading={submitting}
                    disabled={!standardId || !cores || !csa || (needsCoreCountPrompt && !coresTested)}>
              Create Sample
            </Button>
          </Group>
        </Stack>
      </Paper>
    </Stack>
  )
}
