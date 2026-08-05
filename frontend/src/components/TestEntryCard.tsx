import { useState, useEffect } from 'react'
import {
  Card, Stack, Text, Group, Badge, Collapse, NumberInput, SegmentedControl, Select,
  Button, Alert, ActionIcon, Tooltip,
} from '@mantine/core'
import { notifications } from '@mantine/notifications'
import {
  IconChevronDown, IconChevronUp, IconAlertTriangle, IconRepeat, IconWand, IconCheck, IconCircleCheck,
} from '@tabler/icons-react'
import { api, extractErrorMessage } from '../api/client'
import { StatusBadge } from './StatusBadge'
import { useAuthStore } from '../state/authStore'
import { queueOrSend } from '../offline/queueOrSend'
import { sendTestSubmit } from '../offline/sends'
import type { AssignedTestDetail, InputField } from '../types'

const CORE_COLOR_HEX: Record<string, string> = {
  RED: '#C0392B', YELLOW: '#B7950B', BLUE: '#2874A6', BLACK: '#1C2833', SHEATH: '#6C757D',
}

export function CorePositionBadge({ position }: { position: string | null }) {
  if (!position) return null
  return (
    <Badge size="xs" variant="filled" style={{ backgroundColor: CORE_COLOR_HEX[position] ?? '#888' }}>
      {position === 'SHEATH' ? 'Sheath' : position.charAt(0) + position.slice(1).toLowerCase()}
    </Badge>
  )
}

// Sprint Priority 7 (smart data population): the Ageing tests' "before" value
// fields are pre-filled from their sibling Tensile Strength / Elongation at
// Break test's accepted result on the SAME core/sheath position, rather than
// re-typed. Purely a frontend convenience -- the calculation engine still
// treats the field as an explicit raw input (see calculation_engine.py).
const AUTOFILL_SOURCES: Record<string, { fromTestName: string; fromField: 'calculated_value' }> = {
  before_tensile_mpa: { fromTestName: 'Tensile Strength', fromField: 'calculated_value' },
  before_elongation_pct: { fromTestName: 'Elongation at Break', fromField: 'calculated_value' },
}

function TestField({ field, value, onChange, autofillHint }: {
  field: InputField; value: unknown; onChange: (v: unknown) => void; autofillHint?: number | null
}) {
  if (field.type === 'boolean') {
    return (
      <Stack gap={4}>
        <Text size="sm" fw={500}>{field.label}</Text>
        <SegmentedControl
          data={[{ label: 'No', value: 'no' }, { label: 'Yes', value: 'yes' }]}
          value={value === true ? 'yes' : value === false ? 'no' : ''}
          onChange={(v) => onChange(v === 'yes')}
          fullWidth
        />
      </Stack>
    )
  }
  if (field.type === 'select') {
    return (
      <Select
        label={field.label} data={field.options ?? []}
        value={(value as string) ?? null} onChange={onChange}
      />
    )
  }
  if (field.type === 'number_array') {
    const arr = (value as number[]) ?? Array(field.count ?? 5).fill(undefined)
    return (
      <Stack gap={6}>
        <Text size="sm" fw={500}>{field.label} {field.unit ? `(${field.unit})` : ''}</Text>
        <Group gap={6} grow wrap="wrap">
          {Array.from({ length: field.count ?? 5 }).map((_, i) => (
            <NumberInput
              key={i} size="sm" placeholder={`#${i + 1}`} decimalScale={2}
              value={arr[i] as number | undefined}
              onChange={(v) => {
                const next = [...arr]
                next[i] = v as number
                onChange(next)
              }}
            />
          ))}
        </Group>
      </Stack>
    )
  }
  return (
    <NumberInput
      label={`${field.label}${field.unit ? ` (${field.unit})` : ''}`} decimalScale={3}
      value={(value as number | undefined) ?? field.default}
      onChange={onChange}
      rightSection={autofillHint != null ? (
        <Tooltip label={`Autofilled from sibling test: ${autofillHint}`}>
          <IconWand size={14} color="#19376D" />
        </Tooltip>
      ) : undefined}
    />
  )
}

export function TestEntryCard({
  sampleId, test, allTests, onSubmitted, canRepeat, onRequestRepeat, offlineQueue,
}: {
  sampleId: string
  test: AssignedTestDetail
  allTests: AssignedTestDetail[]
  onSubmitted: () => void
  canRepeat?: boolean
  onRequestRepeat?: (assignedTestId: string) => void
  // See ConstructionProfileForm.tsx's identical prop -- opt-in only for the
  // Scientific Assistant's mobile flow.
  offlineQueue?: boolean
}) {
  const [open, setOpen] = useState(false)
  const [values, setValues] = useState<Record<string, unknown>>({})
  const [submitting, setSubmitting] = useState(false)
  const [verifying, setVerifying] = useState(false)
  const canEnter = test.status === 'PENDING' || test.status === 'REPEAT_REQUIRED'
  const role = useAuthStore((s) => s.user?.role)

  async function verify() {
    setVerifying(true)
    try {
      await api.post(`/samples/${sampleId}/tests/${test.assigned_test_id}/verify`)
      notifications.show({ title: 'Reading verified', message: test.name, color: 'teal', icon: <IconCheck size={16} /> })
      onSubmitted()
    } catch (err: unknown) {
      notifications.show({ title: 'Could not verify reading', message: extractErrorMessage(err), color: 'red' })
    } finally {
      setVerifying(false)
    }
  }

  useEffect(() => {
    if (!open) return
    // apply autofill defaults the first time the card opens
    setValues((prev) => {
      const next = { ...prev }
      for (const f of test.input_schema) {
        if (next[f.key] !== undefined) continue
        const src = AUTOFILL_SOURCES[f.key]
        if (src) {
          const sibling = allTests.find((t) => t.core_position === test.core_position && t.name === src.fromTestName)
          if (sibling?.latest_result?.calculated_value != null) {
            next[f.key] = sibling.latest_result.calculated_value
          }
        } else if (f.type === 'number' && f.default != null) {
          next[f.key] = f.default
        }
      }
      return next
    })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open])

  async function submit() {
    setSubmitting(true)
    try {
      // Always sent (both roles), not just when queueing -- makes every
      // submission idempotent-safe against e.g. a double-click or an axios
      // retry, not just ones that actually got queued offline. See
      // sample_service.py's submit_reading (phase 3a) for the backend side.
      const clientRequestId = crypto.randomUUID()
      if (offlineQueue) {
        const result = await queueOrSend(
          () => sendTestSubmit(sampleId, test.assigned_test_id, values, clientRequestId),
          () => ({
            id: clientRequestId, sampleId, kind: 'TEST_SUBMIT',
            assignedTestId: test.assigned_test_id, payload: { raw_values: values },
          }),
        )
        if (result.status === 'sent') {
          const res = result.data
          notifications.show({
            title: `${test.name}: ${res.data.result}`,
            message: res.data.explanation,
            color: res.data.result === 'PASS' ? 'green' : res.data.result === 'FAIL' ? 'red' : 'orange',
          })
        } else {
          notifications.show({
            title: `${test.name}: saved offline`, color: 'blue',
            message: 'Result will appear once this syncs back online.',
          })
        }
      } else {
        const res = await sendTestSubmit(sampleId, test.assigned_test_id, values, clientRequestId)
        notifications.show({
          title: `${test.name}: ${res.data.result}`,
          message: res.data.explanation,
          color: res.data.result === 'PASS' ? 'green' : res.data.result === 'FAIL' ? 'red' : 'orange',
        })
      }
      setOpen(false)
      onSubmitted()
    } finally {
      setSubmitting(false)
    }
  }

  const allFilled = test.input_schema.every((f) => {
    const v = values[f.key]
    if (f.type === 'number_array') return Array.isArray(v) && v.every((x) => typeof x === 'number' && !Number.isNaN(x))
    return v !== undefined && v !== null && v !== ''
  })

  return (
    <Card withBorder radius="md" p="md">
      <Group justify="space-between" onClick={() => canEnter && setOpen((o) => !o)} style={{ cursor: canEnter ? 'pointer' : 'default' }}>
        <Stack gap={2}>
          <Group gap={6}>
            <Text fw={600} size="sm">{test.name}</Text>
            <CorePositionBadge position={test.core_position} />
            {test.status === 'REPEAT_REQUIRED' && <Badge size="xs" color="orange" variant="light">Repeat</Badge>}
            {!test.mandatory && <Badge size="xs" color="gray" variant="light">Optional</Badge>}
          </Group>
          <Text size="xs" c="dimmed">{test.category}</Text>
        </Stack>
        <Group gap={6}>
          {test.latest_result && <StatusBadge status={test.latest_result.result} size="sm" />}
          {test.latest_result?.performed_by_role && (
            <Text size="xs" c="dimmed">by {test.latest_result.performed_by_role === 'SCIENTIST' ? 'Scientist' : 'Assistant'}</Text>
          )}
          {canRepeat && test.latest_result?.result === 'UNDETERMINED' && onRequestRepeat && (
            <Tooltip label="Request a repeat test">
              <ActionIcon variant="light" color="orange" size="sm"
                          onClick={(e) => { e.stopPropagation(); onRequestRepeat(test.assigned_test_id) }}>
                <IconRepeat size={14} />
              </ActionIcon>
            </Tooltip>
          )}
          {test.status === 'COMPLETED' ? null : canEnter ? (
            open ? <IconChevronUp size={16} /> : <IconChevronDown size={16} />
          ) : null}
        </Group>
      </Group>

      {test.latest_result && test.status === 'COMPLETED' && (
        <Group justify="space-between" align="center" mt={6}>
          <Text size="xs" c="dimmed">
            {test.latest_result.calculated_value} {test.latest_result.calculated_unit}
          </Text>
          {test.latest_result.verified ? (
            <Tooltip label={`Verified by ${test.latest_result.verified_by?.full_name ?? 'Scientist'}${test.latest_result.verified_at ? ' · ' + new Date(test.latest_result.verified_at).toLocaleString() : ''}`}>
              <Badge size="xs" color="teal" variant="light" leftSection={<IconCircleCheck size={12} />}>Verified</Badge>
            </Tooltip>
          ) : role === 'SCIENTIST' ? (
            <Button
              size="compact-xs" variant="light" color="teal" leftSection={<IconCircleCheck size={12} />}
              loading={verifying} onClick={(e) => { e.stopPropagation(); verify() }}
            >
              Verify
            </Button>
          ) : null}
        </Group>
      )}

      {canEnter && (
        <Collapse expanded={open}>
          <Stack gap="sm" mt="md">
            {test.status === 'REPEAT_REQUIRED' && test.latest_result && (
              <Alert color="orange" icon={<IconAlertTriangle size={16} />} variant="light">
                {test.latest_result.explanation}
              </Alert>
            )}
            {test.input_schema.map((f) => {
              const src = AUTOFILL_SOURCES[f.key]
              const hint = src && typeof values[f.key] === 'number' ? (values[f.key] as number) : null
              return (
                <TestField key={f.key} field={f} value={values[f.key]}
                           onChange={(v) => setValues((s) => ({ ...s, [f.key]: v }))}
                           autofillHint={hint} />
              )
            })}
            <Button size="sm" onClick={submit} loading={submitting} disabled={!allFilled}>
              Submit Reading
            </Button>
          </Stack>
        </Collapse>
      )}
    </Card>
  )
}
