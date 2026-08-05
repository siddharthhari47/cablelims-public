import { Box, Text } from '@mantine/core'
import type { ArmourType } from '../types'

// Schematic (not-to-scale) concentric-layer cross-section: outer sheath ->
// armour -> inner sheath -> core bundle (insulation + conductor per core).
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

function corePositions(n: number, ringR: number): { x: number; y: number }[] {
  if (n <= 1) return [{ x: 0, y: 0 }]
  const pts = []
  for (let i = 0; i < n; i++) {
    const angle = -Math.PI / 2 + (2 * Math.PI * i) / n
    pts.push({ x: ringR * Math.cos(angle), y: ringR * Math.sin(angle) })
  }
  return pts
}

export function CableDiagram(props: CableDiagramProps) {
  const {
    coresTested, coreColors, conductorMaterial, insulationType, insulationMaterial,
    hasInnerSheath, hasArmour, armourType, armourMaterial, armourStrandCount,
    hasOuterSheath, sheathType, size = 320,
  } = props

  const n = Math.max(coresTested, 1)
  const conductorR = 12
  const insulationR = conductorR + 7
  const coreRingR = n > 1 ? (insulationR + 3) / Math.sin(Math.PI / n) : 0
  const bundleOuterR = coreRingR + insulationR

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
  const scale = Math.min(1, (size / 2 - 20) / naturalExtent)
  const cx = size / 2
  const cy = size / 2

  const cores = corePositions(n, coreRingR)
  const conductorFill = conductorMaterial ? CONDUCTOR_COLOR_HEX[conductorMaterial] ?? '#999' : '#999'

  const strandCount = Math.min(armourStrandCount ?? 24, 48)
  const strandTicks = hasArmour
    ? Array.from({ length: strandCount }, (_, i) => {
        const angle = (2 * Math.PI * i) / strandCount
        const rMid = (armourInnerR + armourOuterR) / 2
        return { x: rMid * Math.cos(angle), y: rMid * Math.sin(angle) }
      })
    : []

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

  return (
    <Box style={{ display: 'flex', gap: 16, flexWrap: 'wrap', alignItems: 'center' }}>
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} role="img" aria-label="Cable cross-section diagram">
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
