import { Box, Text } from '@mantine/core'
import type { ArmourType } from '../types'

// Schematic (not-to-scale) cross-section. Two layouts, chosen by cableShape:
//   Round -- concentric-layer rendering: outer sheath -> armour -> inner
//     sheath -> core bundle, cores arranged in a ring.
//   Flat  -- cores arranged side by side in a row, and every surrounding
//     layer (inner sheath/armour/outer sheath) drawn as a stadium/pill
//     shape (a rounded rectangle with fully-round caps) wrapping that row,
//     instead of a circle -- matching how a real flat cable actually looks.
// Purely a rendering of whatever the profile actually says -- no layer is
// drawn unless its has_* flag is true, and every label reflects the real
// material/colour data entered during profiling, never a guess.

export interface CableDiagramProps {
  coresTested: number
  coreColors: (string | null)[]   // one entry per tested core; null = not yet assigned
  conductorMaterial?: string | null
  insulationType?: string | null
  insulationMaterial?: string | null
  hasInnerSheath: boolean
  hasArmour: boolean
  armourType?: ArmourType | null
  armourMaterial?: string | null
  armourStrandCount?: number | null
  hasOuterSheath: boolean
  sheathType?: string | null
  cableShape?: string | null   // 'Round' | 'Flat' -- anything else falls back to Round
  size?: number
}

const CORE_COLOR_HEX: Record<string, string> = {
  RED: '#c0392b', YELLOW: '#f1c40f', BLUE: '#2166c7', BLACK: '#222222',
}
const CORE_COLOR_STROKE: Record<string, string> = {
  RED: '#7a241b', YELLOW: '#b8960a', BLUE: '#123a72', BLACK: '#000000',
}
const CONDUCTOR_COLOR_HEX: Record<string, string> = {
  Copper: '#b87333', Aluminium: '#b0b0b0',
}

function ringCorePositions(n: number, ringR: number): { x: number; y: number }[] {
  if (n <= 1) return [{ x: 0, y: 0 }]
  const pts = []
  for (let i = 0; i < n; i++) {
    const angle = -Math.PI / 2 + (2 * Math.PI * i) / n
    pts.push({ x: ringR * Math.cos(angle), y: ringR * Math.sin(angle) })
  }
  return pts
}

function rowCorePositions(n: number, spacing: number): { x: number; y: number }[] {
  const half = ((n - 1) * spacing) / 2
  return Array.from({ length: n }, (_, i) => ({ x: -half + i * spacing, y: 0 }))
}

export function CableDiagram(props: CableDiagramProps) {
  const {
    coresTested, coreColors, conductorMaterial, insulationType, insulationMaterial,
    hasInnerSheath, hasArmour, armourType, armourMaterial, armourStrandCount,
    hasOuterSheath, sheathType, cableShape, size = 320,
  } = props

  const isFlat = cableShape === 'Flat'
  const n = Math.max(coresTested, 1)
  const conductorR = 12
  const insulationR = conductorR + 7

  const conductorFill = conductorMaterial ? CONDUCTOR_COLOR_HEX[conductorMaterial] ?? '#999' : '#999'
  const strandCount = Math.min(armourStrandCount ?? 24, 48)

  const legendRows: { swatch: string; label: string }[] = []
  if (hasOuterSheath) {
    legendRows.push({ swatch: '#2b2b2b', label: `Outer Sheath${sheathType ? ` — PVC ${sheathType}` : ''}` })
  }
  if (hasArmour) {
    const parts = [armourType, armourMaterial].filter(Boolean).join(', ')
    legendRows.push({ swatch: '#8a8a8a', label: `Armour${parts ? ` — ${parts}` : ''}${armourStrandCount ? ` (${armourStrandCount} strands)` : ''}` })
  }
  if (hasInnerSheath) {
    legendRows.push({ swatch: '#cfcfcf', label: 'Inner Sheath' })
  }
  for (let i = 0; i < n; i++) {
    const color = coreColors[i]
    legendRows.push({
      swatch: color ? CORE_COLOR_HEX[color] ?? '#ccc' : '#e0e0e0',
      label: `Core ${i + 1}: ${color ?? 'unassigned'}${insulationMaterial ? ` — ${insulationMaterial}` : ''}${insulationType ? ` Type ${insulationType}` : ''} insulation, ${conductorMaterial ?? '?'} conductor`,
    })
  }

  const cx = size / 2
  const cy = size / 2
  let scale: number
  let svgBody: React.ReactNode

  if (isFlat) {
    const coreSpacing = insulationR * 2 + 4
    const cores = rowCorePositions(n, coreSpacing)
    const bundleHalfWidth = (n > 1 ? ((n - 1) * coreSpacing) / 2 : 0) + insulationR
    const bundleHalfHeight = insulationR

    let hw = bundleHalfWidth + 8
    let hh = bundleHalfHeight + 8
    const innerSheathInner = { hw, hh }
    if (hasInnerSheath) { hw += 9; hh += 9 }
    const innerSheathOuter = { hw, hh }

    hw += 6; hh += 6
    const armourInner = { hw, hh }
    if (hasArmour) { hw += 11; hh += 11 }
    const armourOuter = { hw, hh }

    hw += 6; hh += 6
    const outerSheathInner = { hw, hh }
    if (hasOuterSheath) { hw += 15; hh += 15 }
    const outerSheathOuter = { hw, hh }

    const naturalExtent = Math.max(outerSheathOuter.hw, outerSheathOuter.hh) + 10
    scale = Math.min(1, (size / 2 - 20) / naturalExtent)

    // Approximate strand-tick placement on an ellipse through the armour
    // band's midline -- a true stadium boundary isn't elliptical, but this
    // is a schematic ("not to scale") decoration, not a dimensioned drawing.
    const strandTicks = hasArmour
      ? Array.from({ length: strandCount }, (_, i) => {
          const angle = (2 * Math.PI * i) / strandCount
          const rMidHw = (armourInner.hw + armourOuter.hw) / 2
          const rMidHh = (armourInner.hh + armourOuter.hh) / 2
          return { x: rMidHw * Math.cos(angle), y: rMidHh * Math.sin(angle) }
        })
      : []

    const pill = (h: { hw: number; hh: number }, fill: string, key: string) => (
      <rect key={key} x={-h.hw} y={-h.hh} width={h.hw * 2} height={h.hh * 2} rx={h.hh} ry={h.hh} fill={fill} />
    )

    svgBody = (
      <g transform={`translate(${cx} ${cy}) scale(${scale})`}>
        {hasOuterSheath && pill(outerSheathOuter, '#2b2b2b', 'os-out')}
        {hasOuterSheath && pill(outerSheathInner, '#ffffff', 'os-in')}
        {hasArmour && (
          <>
            {pill(armourOuter, '#8a8a8a', 'ar-out')}
            {pill(armourInner, '#ffffff', 'ar-in')}
            {strandTicks.map((p, i) => (
              <circle key={i} cx={p.x} cy={p.y} r={2.2} fill="#5c5c5c" />
            ))}
          </>
        )}
        {hasInnerSheath && (
          <>
            {pill(innerSheathOuter, '#cfcfcf', 'is-out')}
            {pill(innerSheathInner, '#ffffff', 'is-in')}
          </>
        )}
        {cores.map((p, i) => {
          const color = coreColors[i]
          const fill = color ? CORE_COLOR_HEX[color] : '#e0e0e0'
          const stroke = color ? CORE_COLOR_STROKE[color] : '#999'
          return (
            <g key={i} transform={`translate(${p.x} ${p.y})`}>
              <circle r={insulationR} fill={fill} stroke={stroke} strokeWidth={1} />
              <circle r={conductorR} fill={conductorFill} stroke="#5a4326" strokeWidth={0.5} />
            </g>
          )
        })}
      </g>
    )
  } else {
    const coreRingR = n > 1 ? (insulationR + 3) / Math.sin(Math.PI / n) : 0
    const bundleOuterR = coreRingR + insulationR
    const cores = ringCorePositions(n, coreRingR)

    let r = bundleOuterR + 8
    const innerSheathInnerR = r
    if (hasInnerSheath) r += 9
    const innerSheathOuterR = r

    r += 6
    const armourInnerR = r
    if (hasArmour) r += 11
    const armourOuterR = r

    r += 6
    const outerSheathInnerR = r
    if (hasOuterSheath) r += 15
    const outerSheathOuterR = r

    const naturalExtent = outerSheathOuterR + 10
    scale = Math.min(1, (size / 2 - 20) / naturalExtent)

    const strandTicks = hasArmour
      ? Array.from({ length: strandCount }, (_, i) => {
          const angle = (2 * Math.PI * i) / strandCount
          const rMid = (armourInnerR + armourOuterR) / 2
          return { x: rMid * Math.cos(angle), y: rMid * Math.sin(angle) }
        })
      : []

    svgBody = (
      <g transform={`translate(${cx} ${cy}) scale(${scale})`}>
        {hasOuterSheath && (
          <circle r={outerSheathOuterR} fill="#2b2b2b" />
        )}
        {hasOuterSheath && (outerSheathInnerR > 0) && (
          <circle r={outerSheathInnerR} fill="#ffffff" />
        )}
        {hasArmour && (
          <>
            <circle r={armourOuterR} fill="#8a8a8a" />
            <circle r={armourInnerR} fill="#ffffff" />
            {strandTicks.map((p, i) => (
              <circle key={i} cx={p.x} cy={p.y} r={2.2} fill="#5c5c5c" />
            ))}
          </>
        )}
        {hasInnerSheath && (
          <>
            <circle r={innerSheathOuterR} fill="#cfcfcf" />
            <circle r={innerSheathInnerR} fill="#ffffff" />
          </>
        )}
        {cores.map((p, i) => {
          const color = coreColors[i]
          const fill = color ? CORE_COLOR_HEX[color] : '#e0e0e0'
          const stroke = color ? CORE_COLOR_STROKE[color] : '#999'
          return (
            <g key={i} transform={`translate(${p.x} ${p.y})`}>
              <circle r={insulationR} fill={fill} stroke={stroke} strokeWidth={1} />
              <circle r={conductorR} fill={conductorFill} stroke="#5a4326" strokeWidth={0.5} />
            </g>
          )
        })}
      </g>
    )
  }

  return (
    <Box style={{ display: 'flex', gap: 16, flexWrap: 'wrap', alignItems: 'center' }}>
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} role="img" aria-label="Cable cross-section diagram">
        {svgBody}
      </svg>
      <Box style={{ minWidth: 200 }}>
        {legendRows.map((row, i) => (
          <Box key={i} style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
            <Box style={{ width: 12, height: 12, borderRadius: '50%', background: row.swatch, border: '1px solid #999', flexShrink: 0 }} />
            <Text size="xs">{row.label}</Text>
          </Box>
        ))}
        {legendRows.length === 0 && <Text size="xs" c="dimmed">No construction layers set yet.</Text>}
        <Text size="xs" c="dimmed" mt={6} fs="italic">Schematic diagram — not to scale.</Text>
      </Box>
    </Box>
  )
}
