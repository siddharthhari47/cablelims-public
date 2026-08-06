import { useEffect, useRef, useState } from 'react'
import {
  Stack, Text, Card, Select, TextInput, NumberInput, Button, Group, Divider,
  Alert, Switch, SimpleGrid, Badge, SegmentedControl,
} from '@mantine/core'
import { notifications } from '@mantine/notifications'
import { IconCheck, IconInfoCircle, IconUpload, IconCamera } from '@tabler/icons-react'
import { extractErrorMessage } from '../api/client'
import { CableDiagram } from './CableDiagram'
import { queueOrSend } from '../offline/queueOrSend'
import { sendDiagramImage, sendProfile } from '../offline/sends'
import { compressImage } from '../offline/compressImage'
import type { ArmourType } from '../types'

const CONDUCTOR_MATERIALS = ['Copper', 'Aluminium']
const CONDUCTOR_CLASSES = ['1', '2', '5']
// IS 5831:1984 Table 1 insulation compound types (A = general purpose, C =
// heat resisting, D = flexible cords -- D is a CTL-operational designation,
// not in the 1984 edition itself, but CTL actively certifies against it).
const INSULATION_TYPES = ['A', 'C', 'D']
const INSULATION_MATERIALS = ['PVC', 'XLPE', 'PE']
const SHEATH_TYPES = ['ST1', 'ST2', 'ST3', 'None']
const FIRE_CATEGORIES = ['01', '02', 'FR', 'FR-LSH']
const ARMOUR_TYPES: ArmourType[] = ['Steel Wire', 'Steel Strip', 'Steel Tape', 'Aluminium Wire']
const NAMED_CORE_COLORS = ['RED', 'YELLOW', 'BLUE', 'BLACK']

interface Props {
  sampleId: string
  coresTested: number
  suggestedCoreColors: string[] | null
  onSaved: () => void
  // Opt-in only for the Scientific Assistant's mobile flow -- the
  // Scientist's desktop view doesn't need offline queueing and keeps its
  // exact prior behavior (a network failure surfaces as an error) when this
  // is omitted. See ProfileSummaryCard.tsx's `sampleId` prop for the same pattern.
  offlineQueue?: boolean
}

export function ConstructionProfileForm({ sampleId, coresTested, suggestedCoreColors, onSaved, offlineQueue }: Props) {
  const [conductorMaterial, setConductorMaterial] = useState('Copper')
  const [conductorClass, setConductorClass] = useState('2')
  const [insulationType, setInsulationType] = useState('A')
  const [insulationMaterial, setInsulationMaterial] = useState('PVC')
  const [sheathType, setSheathType] = useState<string | null>('ST1')
  const [fireCategory, setFireCategory] = useState('01')
  const [construction, setConstruction] = useState('')
  const [cableShape, setCableShape] = useState<'Round' | 'Flat'>('Round')
  const [overallDiameter, setOverallDiameter] = useState<number | ''>('')
  const [diameterUnderSheath, setDiameterUnderSheath] = useState<number | ''>('')
  // IS 694 cl.22, Table 10 -- a flat cable's overall dimensions are Width x
  // Height, not a diameter. Genuinely different fields from OD/ID above,
  // shown instead of them (not alongside) when Flat is selected.
  const [flatWidth, setFlatWidth] = useState<number | ''>('')
  const [flatHeight, setFlatHeight] = useState<number | ''>('')

  const [hasArmour, setHasArmour] = useState(false)
  const [hasInnerSheath, setHasInnerSheath] = useState(false)
  const [armourType, setArmourType] = useState<ArmourType | null>(null)
  const [armourMaterial, setArmourMaterial] = useState('')
  const [armourStrandCount, setArmourStrandCount] = useState<number | ''>('')

  // One entry per tested core, in physical position order -- the Scientist
  // /Assistant must explicitly assign every one before this form can submit.
  // A suggested sequence pre-fills the fields (for the <=4-core case only)
  // as a convenience, but nothing here is applied silently: the user still
  // sees and can change every value before Confirm.
  const [coreAssignments, setCoreAssignments] = useState<(string | null)[]>(
    () => Array.from({ length: coresTested }, () => null),
  )

  const [saving, setSaving] = useState(false)
  const diagramFileRef = useRef<HTMLInputElement>(null)
  const [diagramUploaded, setDiagramUploaded] = useState(false)

  useEffect(() => {
    setCoreAssignments(Array.from({ length: coresTested }, () => null))
  }, [coresTested])

  const namedColors = coresTested <= NAMED_CORE_COLORS.length

  function applySuggested() {
    if (suggestedCoreColors) setCoreAssignments([...suggestedCoreColors])
  }

  function setCore(i: number, value: string) {
    setCoreAssignments((prev) => prev.map((v, idx) => (idx === i ? value : v)))
  }

  const allAssigned = coreAssignments.every((c) => c && c.trim().length > 0)
  const distinctOk = !namedColors || new Set(coreAssignments).size === coreAssignments.length
  const canSubmit = allAssigned && distinctOk

  async function handleDiagramFile(e: React.ChangeEvent<HTMLInputElement>) {
    const rawFile = e.target.files?.[0]
    if (!rawFile) return
    try {
      const file = await compressImage(rawFile)
      if (offlineQueue) {
        const result = await queueOrSend(
          () => sendDiagramImage(sampleId, file, file.name),
          () => ({ id: crypto.randomUUID(), sampleId, kind: 'DIAGRAM_IMAGE', payload: { blob: file, filename: file.name } }),
        )
        setDiagramUploaded(true)
        if (result.status === 'sent') {
          notifications.show({ title: 'Diagram uploaded', message: 'This will be used in place of the generated diagram', color: 'green' })
        } else {
          notifications.show({ title: 'Diagram saved offline', message: 'Will upload once back online', color: 'blue' })
        }
      } else {
        await sendDiagramImage(sampleId, file, file.name)
        setDiagramUploaded(true)
        notifications.show({ title: 'Diagram uploaded', message: 'This will be used in place of the generated diagram', color: 'green' })
      }
    } catch (err: unknown) {
      notifications.show({ title: 'Could not upload diagram', message: extractErrorMessage(err), color: 'red' })
    }
  }

  async function submit() {
    setSaving(true)
    const body = {
      conductor_material: conductorMaterial, conductor_class: conductorClass,
      insulation_type: insulationType, insulation_material: insulationMaterial,
      sheath_type: sheathType === 'None' ? null : sheathType,
      fire_category: fireCategory, construction,
      tested_core_colors: coreAssignments,
      has_outer_sheath: sheathType !== 'None',
      has_armour: hasArmour, has_inner_sheath: hasInnerSheath,
      armour_type: hasArmour ? armourType : null,
      armour_material: hasArmour ? armourMaterial : null,
      armour_strand_count: hasArmour ? (armourStrandCount === '' ? null : armourStrandCount) : null,
      cable_shape: cableShape,
      // Only the dimension pair for the selected shape is sent -- the other
      // pair is cleared rather than left over from a shape toggle earlier
      // in this session.
      overall_diameter_mm: cableShape === 'Round' && overallDiameter !== '' ? overallDiameter : null,
      diameter_under_sheath_mm: cableShape === 'Round' && diameterUnderSheath !== '' ? diameterUnderSheath : null,
      flat_width_mm: cableShape === 'Flat' && flatWidth !== '' ? flatWidth : null,
      flat_height_mm: cableShape === 'Flat' && flatHeight !== '' ? flatHeight : null,
    }
    try {
      if (offlineQueue) {
        const result = await queueOrSend(
          () => sendProfile(sampleId, body),
          () => ({ id: crypto.randomUUID(), sampleId, kind: 'PROFILE', payload: body }),
        )
        if (result.status === 'sent') {
          notifications.show({ title: 'Profile confirmed', message: 'Tests assigned automatically', color: 'green', icon: <IconCheck size={16} /> })
          onSaved()
        } else {
          notifications.show({
            title: 'Profile saved offline', color: 'blue',
            message: 'Will be confirmed and tests assigned once back online -- reopen this sample then to enter readings.',
          })
        }
      } else {
        await sendProfile(sampleId, body)
        notifications.show({ title: 'Profile confirmed', message: 'Tests assigned automatically', color: 'green', icon: <IconCheck size={16} /> })
        onSaved()
      }
    } catch (err: unknown) {
      notifications.show({ title: 'Could not confirm profile', message: extractErrorMessage(err), color: 'red' })
    } finally {
      setSaving(false)
    }
  }

  return (
    <Stack gap="md">
      <Text fw={700}>Cable Profile</Text>

      <SimpleGrid cols={{ base: 1, sm: 2 }} spacing="sm">
        <Select label="Conductor Material" data={CONDUCTOR_MATERIALS} value={conductorMaterial} onChange={(v) => v && setConductorMaterial(v)} allowDeselect={false} />
        <Select label="Conductor Class (IS 8130)" data={CONDUCTOR_CLASSES} value={conductorClass} onChange={(v) => v && setConductorClass(v)} allowDeselect={false} />
        <Select label="Insulation Type (IS 5831 Table 1)" data={INSULATION_TYPES} value={insulationType} onChange={(v) => v && setInsulationType(v)} allowDeselect={false}
                description="A = general purpose, C = heat resisting, D = flexible cords" />
        <Select label="Insulation Material" data={INSULATION_MATERIALS} value={insulationMaterial} onChange={(v) => v && setInsulationMaterial(v)} allowDeselect={false} />
        <Select label="Sheath Type (IS 5831 Table 2)" data={SHEATH_TYPES} value={sheathType ?? 'None'} onChange={setSheathType} allowDeselect={false} />
        <Select label="Fire Category" data={FIRE_CATEGORIES} value={fireCategory} onChange={(v) => v && setFireCategory(v)} allowDeselect={false} />
      </SimpleGrid>
      <TextInput label="Construction (free text)" placeholder="e.g. 3 core, sheathed" value={construction} onChange={(e) => setConstruction(e.currentTarget.value)} />

      <Divider label="Dimensions" labelPosition="left" />
      <SimpleGrid cols={{ base: 1, sm: 3 }} spacing="sm">
        <Stack gap={4}>
          <Text size="sm" fw={500}>Cable Shape</Text>
          <SegmentedControl
            fullWidth data={['Round', 'Flat']} value={cableShape}
            onChange={(v) => setCableShape(v as 'Round' | 'Flat')}
          />
        </Stack>
        {cableShape === 'Round' ? (
          <>
            <NumberInput
              label="Overall Diameter (OD)" description="Measured over the finished cable" suffix=" mm"
              value={overallDiameter} onChange={(v) => setOverallDiameter(v === '' ? '' : Number(v))}
              decimalScale={2} min={0}
            />
            <NumberInput
              label="Diameter Under Sheath (ID)" description="Over laid-up cores, before outer sheath" suffix=" mm"
              value={diameterUnderSheath} onChange={(v) => setDiameterUnderSheath(v === '' ? '' : Number(v))}
              decimalScale={2} min={0}
            />
          </>
        ) : (
          <>
            <NumberInput
              label="Width (W)" description="IS 694 cl.22, Table 10 — the longer overall dimension" suffix=" mm"
              value={flatWidth} onChange={(v) => setFlatWidth(v === '' ? '' : Number(v))}
              decimalScale={2} min={0}
            />
            <NumberInput
              label="Height (H)" description="The shorter overall dimension" suffix=" mm"
              value={flatHeight} onChange={(v) => setFlatHeight(v === '' ? '' : Number(v))}
              decimalScale={2} min={0}
            />
          </>
        )}
      </SimpleGrid>
      {cableShape === 'Flat' && coresTested > 3 && (
        <Alert color="yellow" variant="light" icon={<IconInfoCircle size={16} />}>
          IS 694 cl.22 only defines flat-cable construction and dimensions for 2-core and 3-core
          cables — this sample has {coresTested}. Recording it as Flat is still allowed, but its
          dimensions won't match a published table entry; note that in Construction (free text) if
          relevant.
        </Alert>
      )}

      <Divider label="Construction Layers" labelPosition="left" />

      <Group>
        <Switch label="Has Inner Sheath" checked={hasInnerSheath} onChange={(e) => setHasInnerSheath(e.currentTarget.checked)} />
        <Switch label="Has Armour" checked={hasArmour} onChange={(e) => setHasArmour(e.currentTarget.checked)} />
      </Group>
      {hasArmour && (
        <SimpleGrid cols={{ base: 1, sm: 3 }} spacing="sm">
          <Select label="Armour Type" data={ARMOUR_TYPES} value={armourType} onChange={(v) => setArmourType(v as ArmourType)} placeholder="Select type" />
          <TextInput label="Armour Material" placeholder="e.g. Galvanized Steel" value={armourMaterial} onChange={(e) => setArmourMaterial(e.currentTarget.value)} />
          <NumberInput label="Strand Count" value={armourStrandCount} onChange={(v) => setArmourStrandCount(v === '' ? '' : Number(v))} min={1} />
        </SimpleGrid>
      )}

      <Divider label="Core Colour Assignment" labelPosition="left" />
      <Alert color="blue" variant="light" icon={<IconInfoCircle size={16} />}>
        Each core must be explicitly assigned before the profile can be confirmed. Colours are never assigned automatically.
      </Alert>
      {namedColors && suggestedCoreColors && (
        <Button size="xs" variant="light" w="fit-content" onClick={applySuggested}>
          Pre-fill suggested sequence ({suggestedCoreColors.join(', ')}) — review before confirming
        </Button>
      )}
      <SimpleGrid cols={{ base: 2, sm: 4 }} spacing="sm">
        {coreAssignments.map((val, i) => (
          namedColors ? (
            <Select
              key={i} label={`Core ${i + 1}`} placeholder="Assign colour"
              data={NAMED_CORE_COLORS} value={val} onChange={(v) => setCore(i, v ?? '')}
            />
          ) : (
            <TextInput
              key={i} label={`Core ${i + 1}`} placeholder="e.g. Core-01"
              value={val ?? ''} onChange={(e) => setCore(i, e.currentTarget.value)}
            />
          )
        ))}
      </SimpleGrid>
      {namedColors && !distinctOk && (
        <Text size="xs" c="red">Each core must have a distinct colour.</Text>
      )}

      <Divider label="Cross-Section Preview" labelPosition="left" />
      <CableDiagram
        coresTested={coresTested}
        coreColors={coreAssignments}
        conductorMaterial={conductorMaterial}
        insulationType={insulationType}
        insulationMaterial={insulationMaterial}
        hasInnerSheath={hasInnerSheath}
        hasArmour={hasArmour}
        armourType={armourType}
        armourMaterial={armourMaterial}
        armourStrandCount={typeof armourStrandCount === 'number' ? armourStrandCount : null}
        hasOuterSheath={sheathType !== 'None'}
        sheathType={sheathType}
        cableShape={cableShape}
      />

      <Divider label="Doesn't match a real cable? Upload a hand-drawn/photographed diagram instead" labelPosition="left" />
      <Card withBorder radius="md" p="md" onClick={() => diagramFileRef.current?.click()} style={{ cursor: 'pointer', borderStyle: 'dashed' }}>
        <input ref={diagramFileRef} type="file" accept="image/*" capture="environment" hidden onChange={handleDiagramFile} />
        <Group justify="center" gap="xs" py="sm">
          {diagramUploaded ? <IconCheck size={20} color="green" /> : <IconUpload size={20} color="#19376D" />}
          <Text size="sm" c={diagramUploaded ? 'green' : 'dimmed'}>
            {diagramUploaded ? 'Diagram uploaded — will replace the generated preview above' : 'Tap to upload a diagram (used instead of the generated one)'}
          </Text>
          <IconCamera size={16} color="#19376D" style={{ display: diagramUploaded ? 'none' : undefined }} />
        </Group>
      </Card>

      {!canSubmit && (
        <Badge color="orange" variant="light" w="fit-content">Assign every core's colour to continue</Badge>
      )}
      <Button size="md" mt="xs" onClick={submit} loading={saving} disabled={!canSubmit}>
        Confirm Profile &amp; Assign Tests
      </Button>
    </Stack>
  )
}
