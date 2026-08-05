import { useState } from 'react'
import {
  Text, Table, Badge, Group, ActionIcon, Tooltip, Switch, Modal, Stack, Divider, Title, ThemeIcon,
  Select, NumberInput, Textarea, Button, Alert,
} from '@mantine/core'
import {
  IconInfoCircle, IconRepeat, IconRuler, IconCalculator, IconClipboardCheck, IconTargetArrow,
  IconEdit, IconGavel, IconAlertTriangle,
} from '@tabler/icons-react'
import { StatusBadge } from './StatusBadge'
import { CorePositionBadge } from './TestEntryCard'
import type { AssignedTestDetail, InputField } from '../types'

// Mirrors Test Report_694.docx's own grouping (IS 694:2010 Table 1, Sl. No.
// iii's lettered sections) so the in-app Calculation view reads as the same
// report structure a Scientist already knows, not a generic results dump.
const SECTION_LABELS: Record<string, string> = {
  CONDUCTOR: 'a. Test on Conductor',
  DIMENSIONAL: 'b. Overall Dimensions & Thickness of Insulation and Sheath',
  PHYSICAL: 'c. Physical Test on Insulation (and Sheath)',
  COMPLETED_CABLE: 'd. Test on Completed Cable',
}
const SECTION_ORDER = ['CONDUCTOR', 'DIMENSIONAL', 'PHYSICAL', 'COMPLETED_CABLE']
const POSITION_ORDER = ['RED', 'YELLOW', 'BLUE', 'BLACK', 'SHEATH']

interface Props {
  tests: AssignedTestDetail[]
  locked: boolean
  onToggle: (assignedTestId: string, enabled: boolean) => void
  onRepeat: (assignedTestId: string) => void
  onOverride: (assignedTestId: string, body: { result: string; limit_value: number | null; reason: string }) => Promise<void>
  busy: boolean
}

export function CalculationMatrix({ tests, locked, onToggle, onRepeat, onOverride, busy }: Props) {
  const [procedureTest, setProcedureTest] = useState<AssignedTestDetail | null>(null)
  const [overrideTest, setOverrideTest] = useState<AssignedTestDetail | null>(null)

  const bySection: Record<string, AssignedTestDetail[]> = {}
  for (const t of tests) {
    const key = t.report_section ?? 'OTHER'
    bySection[key] = bySection[key] ?? []
    bySection[key].push(t)
  }
  const sectionKeys = [
    ...SECTION_ORDER.filter((k) => bySection[k]?.length),
    ...Object.keys(bySection).filter((k) => !SECTION_ORDER.includes(k)),
  ]

  if (tests.length === 0) {
    return <Text c="dimmed" size="sm">No tests assigned yet.</Text>
  }

  return (
    <Stack gap="lg">
      {sectionKeys.map((sectionKey) => {
        const sectionTests = bySection[sectionKey]
        const byTestId: Record<string, AssignedTestDetail[]> = {}
        for (const t of sectionTests) {
          byTestId[t.test_id] = byTestId[t.test_id] ?? []
          byTestId[t.test_id].push(t)
        }
        const testIds = Object.keys(byTestId).sort(
          (a, b) => sectionTests.indexOf(byTestId[a][0]) - sectionTests.indexOf(byTestId[b][0]),
        )
        const positionsPresent = POSITION_ORDER.filter((p) => sectionTests.some((t) => t.core_position === p))
        const hasWholeSample = sectionTests.some((t) => t.core_position == null)

        return (
          <div key={sectionKey}>
            <Text fw={700} mb="xs">{SECTION_LABELS[sectionKey] ?? sectionKey}</Text>
            <Table.ScrollContainer minWidth={640}>
              <Table verticalSpacing="sm" highlightOnHover withTableBorder>
                <Table.Thead>
                  <Table.Tr>
                    <Table.Th>Test</Table.Th>
                    <Table.Th>Specified</Table.Th>
                    {hasWholeSample && <Table.Th>Observed</Table.Th>}
                    {positionsPresent.map((p) => (
                      <Table.Th key={p}><CorePositionBadge position={p} /></Table.Th>
                    ))}
                  </Table.Tr>
                </Table.Thead>
                <Table.Tbody>
                  {testIds.map((tid) => {
                    const rows = byTestId[tid]
                    const first = rows[0]
                    const byPos: Record<string, AssignedTestDetail> = {}
                    for (const r of rows) byPos[r.core_position ?? 'WHOLE'] = r
                    const withResult = rows.find((r) => r.latest_result)
                    const lr = withResult?.latest_result

                    return (
                      <Table.Tr key={tid}>
                        <Table.Td>
                          <Group gap={4} wrap="nowrap" align="flex-start">
                            <Stack gap={0}>
                              <Text fw={600} size="sm">{first.name}</Text>
                              {first.clause_reference && (
                                <Text size="xs" c="dimmed">{first.clause_reference}</Text>
                              )}
                            </Stack>
                            {!first.mandatory && (
                              <Switch
                                size="xs" checked={first.enabled} disabled={locked}
                                onChange={(e) => rows.forEach((r) => onToggle(r.assigned_test_id, e.currentTarget.checked))}
                              />
                            )}
                            {first.procedure_summary && (
                              <Tooltip label="View calculation procedure, in plain terms">
                                <ActionIcon
                                  size="sm" variant="light" color="blue"
                                  onClick={() => setProcedureTest(withResult ?? first)}
                                >
                                  <IconInfoCircle size={14} />
                                </ActionIcon>
                              </Tooltip>
                            )}
                          </Group>
                        </Table.Td>
                        <Table.Td>
                          {lr && lr.limit_source_kind === 'VERIFIED' && lr.limit_value != null ? (
                            <Tooltip label={`Source: ${lr.limit_source_ref ?? 'not recorded'}`} multiline w={280}>
                              <Text size="xs" style={{ cursor: 'help', borderBottom: '1px dotted currentColor' }}>
                                {lr.limit_operator} {lr.limit_value} {first.unit}
                              </Text>
                            </Tooltip>
                          ) : lr?.limit_source_kind === 'MISSING' ? (
                            <Tooltip label={lr.explanation} multiline w={280}>
                              <Badge size="xs" color="red" variant="light">No criterion yet</Badge>
                            </Tooltip>
                          ) : lr?.limit_source_kind === 'PLACEHOLDER' ? (
                            <Tooltip label={lr.explanation} multiline w={280}>
                              <Badge size="xs" color="yellow" variant="light">Pending verification</Badge>
                            </Tooltip>
                          ) : '—'}
                        </Table.Td>
                        {hasWholeSample && (
                          <Table.Td>
                            <CellValue t={byPos.WHOLE} locked={locked} onRepeat={onRepeat} onOverrideClick={setOverrideTest} busy={busy} />
                          </Table.Td>
                        )}
                        {positionsPresent.map((p) => (
                          <Table.Td key={p}>
                            <CellValue t={byPos[p]} locked={locked} onRepeat={onRepeat} onOverrideClick={setOverrideTest} busy={busy} />
                          </Table.Td>
                        ))}
                      </Table.Tr>
                    )
                  })}
                </Table.Tbody>
              </Table>
            </Table.ScrollContainer>
          </div>
        )
      })}

      <ProcedureModal test={procedureTest} onClose={() => setProcedureTest(null)} />
      <OverrideModal
        test={overrideTest}
        busy={busy}
        onClose={() => setOverrideTest(null)}
        onSubmit={async (body) => {
          if (!overrideTest) return
          await onOverride(overrideTest.assigned_test_id, body)
          setOverrideTest(null)
        }}
      />
    </Stack>
  )
}

function CellValue({ t, locked, onRepeat, onOverrideClick, busy }: {
  t?: AssignedTestDetail; locked: boolean; onRepeat: (id: string) => void
  onOverrideClick: (t: AssignedTestDetail) => void; busy: boolean
}) {
  if (!t) return <Text size="xs" c="dimmed">—</Text>
  const lr = t.latest_result
  return (
    <Group gap={4} wrap="nowrap" align="center">
      <Stack gap={2}>
        {lr?.calculated_value != null ? (
          <Text size="sm">{lr.calculated_value} {lr.calculated_unit}</Text>
        ) : <Text size="xs" c="dimmed">—</Text>}
        <Group gap={4}>
          <StatusBadge status={lr?.effective_result ?? 'PENDING'} size="xs" />
          {lr?.overridden && (
            <Tooltip
              label={`Overridden by ${lr.overridden_by?.full_name ?? 'Scientist'}: ${lr.override_reason ?? ''}`}
              multiline w={260}
            >
              <ThemeIcon size={16} radius="xl" color="grape" variant="light" style={{ cursor: 'help' }}>
                <IconGavel size={10} />
              </ThemeIcon>
            </Tooltip>
          )}
        </Group>
      </Stack>
      {lr && lr.effective_result === 'UNDETERMINED' && !locked && (
        <Tooltip label="Request a repeat test">
          <ActionIcon size="sm" variant="light" color="orange" onClick={() => onRepeat(t.assigned_test_id)} loading={busy}>
            <IconRepeat size={12} />
          </ActionIcon>
        </Tooltip>
      )}
      {lr && !locked && (
        <Tooltip label="Override this result">
          <ActionIcon size="sm" variant="subtle" color="grape" onClick={() => onOverrideClick(t)}>
            <IconEdit size={12} />
          </ActionIcon>
        </Tooltip>
      )}
    </Group>
  )
}

function formatRawValue(field: InputField, raw: Record<string, unknown>): string {
  const v = raw[field.key]
  if (v == null) return '—'
  if (Array.isArray(v)) return v.map((x) => String(x)).join(', ') + (field.unit ? ` ${field.unit}` : '')
  if (typeof v === 'boolean') return v ? 'Yes' : 'No'
  return `${v}${field.unit ? ` ${field.unit}` : ''}`
}

function ProcedureModal({ test, onClose }: { test: AssignedTestDetail | null; onClose: () => void }) {
  const lr = test?.latest_result
  return (
    <Modal
      opened={!!test} onClose={onClose} title={test ? <Title order={4}>{test.name}</Title> : ''}
      size="lg" centered
    >
      {test && (
        <Stack gap="lg">
          <Group gap={6}>
            {test.core_position && <CorePositionBadge position={test.core_position} />}
            {test.clause_reference && <Badge variant="light" color="gray">{test.clause_reference}</Badge>}
          </Group>

          {test.procedure_summary && (
            <ProcedureSection icon={<IconTargetArrow size={16} />} color="blue" title="What this checks">
              <Text size="sm">{test.procedure_summary}</Text>
            </ProcedureSection>
          )}

          {test.procedure_measurement && (
            <ProcedureSection icon={<IconRuler size={16} />} color="teal" title="How it's measured">
              <Text size="sm">{test.procedure_measurement}</Text>
            </ProcedureSection>
          )}

          {test.procedure_formula && (
            <ProcedureSection icon={<IconCalculator size={16} />} color="grape" title="Formula">
              <Text size="sm" style={{ whiteSpace: 'pre-wrap' }}>{test.procedure_formula}</Text>
            </ProcedureSection>
          )}

          {lr && (
            <ProcedureSection icon={<IconClipboardCheck size={16} />} color="green" title="This sample's recorded numbers">
              <Stack gap={6}>
                {test.input_schema.map((field) => (
                  <Group key={field.key} justify="space-between" gap="md">
                    <Text size="sm" c="dimmed">{field.label}</Text>
                    <Text size="sm" fw={500}>{formatRawValue(field, lr.raw_values)}</Text>
                  </Group>
                ))}
                <Divider />
                <Group justify="space-between" gap="md">
                  <Text size="sm" fw={700}>Result</Text>
                  <Group gap={8}>
                    <Text size="sm" fw={700}>
                      {lr.calculated_value != null ? `${lr.calculated_value} ${lr.calculated_unit ?? ''}` : '—'}
                    </Text>
                    <StatusBadge status={lr.effective_result} size="sm" />
                  </Group>
                </Group>
                {lr.limit_value != null && (
                  <Group justify="space-between" gap="md">
                    <Text size="xs" c="dimmed">Required</Text>
                    <Text size="xs" c="dimmed">{lr.limit_operator} {lr.limit_value} {lr.calculated_unit}</Text>
                  </Group>
                )}
                {lr.limit_source_ref && (
                  <Group justify="space-between" gap="md">
                    <Text size="xs" c="dimmed">Source</Text>
                    <Text size="xs" c="dimmed" ta="right">{lr.limit_source_ref}</Text>
                  </Group>
                )}
              </Stack>
            </ProcedureSection>
          )}

          {lr?.overridden && (
            <ProcedureSection icon={<IconGavel size={16} />} color="grape" title="Scientist override">
              <Stack gap={6}>
                <Group justify="space-between" gap="md">
                  <Text size="xs" c="dimmed">System originally computed</Text>
                  <StatusBadge status={lr.result} size="xs" />
                </Group>
                {lr.override_limit_value != null && (
                  <Group justify="space-between" gap="md">
                    <Text size="xs" c="dimmed">Limit used instead</Text>
                    <Text size="xs" c="dimmed">{lr.limit_operator} {lr.override_limit_value}</Text>
                  </Group>
                )}
                <Group justify="space-between" gap="md">
                  <Text size="xs" c="dimmed">Overridden by</Text>
                  <Text size="xs" c="dimmed">{lr.overridden_by?.full_name} &middot; {lr.overridden_at ? new Date(lr.overridden_at).toLocaleString() : ''}</Text>
                </Group>
                <Text size="sm" fs="italic">&ldquo;{lr.override_reason}&rdquo;</Text>
              </Stack>
            </ProcedureSection>
          )}
        </Stack>
      )}
    </Modal>
  )
}

function ProcedureSection({ icon, color, title, children }: {
  icon: React.ReactNode; color: string; title: string; children: React.ReactNode
}) {
  return (
    <Stack gap={6}>
      <Group gap={8}>
        <ThemeIcon size={24} radius="xl" color={color} variant="light">{icon}</ThemeIcon>
        <Text fw={700} size="sm">{title}</Text>
      </Group>
      <div style={{ paddingLeft: 32 }}>{children}</div>
    </Stack>
  )
}

function OverrideModal({ test, busy, onClose, onSubmit }: {
  test: AssignedTestDetail | null
  busy: boolean
  onClose: () => void
  onSubmit: (body: { result: string; limit_value: number | null; reason: string }) => Promise<void>
}) {
  const lr = test?.latest_result
  const [result, setResult] = useState<string | null>('PASS')
  const [limitValue, setLimitValue] = useState<number | ''>('')
  const [reason, setReason] = useState('')

  // Reset the form fresh whenever a different test is opened for override.
  const key = test?.assigned_test_id ?? ''
  const [lastKey, setLastKey] = useState('')
  if (key !== lastKey) {
    setLastKey(key)
    setResult(lr?.effective_result === 'FAIL' ? 'FAIL' : 'PASS')
    setLimitValue(lr?.limit_value ?? '')
    setReason('')
  }

  const canSubmit = !!result && reason.trim().length >= 10

  return (
    <Modal opened={!!test} onClose={onClose} title={<Title order={4}>Override Result</Title>} size="md" centered>
      {test && (
        <Stack gap="md">
          <Group gap={6}>
            <Text fw={600} size="sm">{test.name}</Text>
            {test.core_position && <CorePositionBadge position={test.core_position} />}
          </Group>

          <Alert icon={<IconAlertTriangle size={16} />} color="grape" variant="light">
            Overriding never changes the recorded measurement or the system's own calculation --
            it layers a documented Scientist decision on top. The original system result stays
            visible for audit.
          </Alert>

          <Group grow>
            <Stack gap={2}>
              <Text size="xs" c="dimmed">Measured value</Text>
              <Text size="sm" fw={600}>{lr?.calculated_value != null ? `${lr.calculated_value} ${lr.calculated_unit ?? ''}` : '—'}</Text>
            </Stack>
            <Stack gap={2}>
              <Text size="xs" c="dimmed">System result</Text>
              <StatusBadge status={lr?.result ?? 'PENDING'} size="sm" />
            </Stack>
          </Group>

          <NumberInput
            label="Limit you believe is correct (optional)"
            description="Recorded for the audit trail -- the final decision below is still what counts"
            value={limitValue}
            onChange={(v) => setLimitValue(v === '' ? '' : Number(v))}
            decimalScale={4}
          />

          <Select
            label="Final decision" required
            data={[{ value: 'PASS', label: 'PASS' }, { value: 'FAIL', label: 'FAIL' }]}
            value={result} onChange={setResult} allowDeselect={false}
          />

          <Textarea
            label="Reason (required)" required minRows={2}
            placeholder="Why is the system's own result being overridden?"
            value={reason} onChange={(e) => setReason(e.currentTarget.value)}
          />

          <Group justify="flex-end">
            <Button variant="default" onClick={onClose}>Cancel</Button>
            <Button
              color="grape" loading={busy} disabled={!canSubmit}
              onClick={() => result && onSubmit({ result, limit_value: limitValue === '' ? null : limitValue, reason })}
            >
              Confirm Override
            </Button>
          </Group>
        </Stack>
      )}
    </Modal>
  )
}
