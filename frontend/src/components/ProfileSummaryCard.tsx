import { useEffect, useState } from 'react'
import { Paper, Text, Group, Badge, Image, Stack, Loader, Center } from '@mantine/core'
import { CableDiagram } from './CableDiagram'
import { api } from '../api/client'
import { getCachedImage, putCachedImage } from '../offline/db'
import { isNetworkError } from '../offline/isNetworkError'
import type { CableProfile } from '../types'

// A plain <img src> can't carry the app's Bearer token (only axios calls
// get it, via the request interceptor in api/client.ts) -- the diagram
// endpoint requires auth, so a bare <Image src={url}> silently fails to
// load. Fetch it through the authenticated client and use an object URL
// instead.
//
// `cacheKey` is optional and only passed by the Scientific Assistant's
// mobile flow (AssistantSamplePage) -- the Scientist's desktop view doesn't
// need offline support, so passing nothing here leaves its behavior exactly
// as it was before offline support existed: a plain fetch, no IndexedDB
// fallback on failure.
function useAuthenticatedImage(url: string | null | undefined, cacheKey?: string): string | null {
  const [objectUrl, setObjectUrl] = useState<string | null>(null)
  useEffect(() => {
    if (!url) { setObjectUrl(null); return }
    let revoked = ''
    async function load() {
      try {
        const res = await api.get(url!, { responseType: 'blob' })
        const blobUrl = URL.createObjectURL(res.data)
        revoked = blobUrl
        setObjectUrl(blobUrl)
        if (cacheKey) putCachedImage(cacheKey, res.data, res.data.type || 'image/jpeg')
      } catch (err) {
        if (!cacheKey || !isNetworkError(err)) throw err
        const cached = await getCachedImage(cacheKey)
        if (cached) {
          const blobUrl = URL.createObjectURL(cached.blob)
          revoked = blobUrl
          setObjectUrl(blobUrl)
        }
      }
    }
    load()
    return () => { if (revoked) URL.revokeObjectURL(revoked) }
  }, [url, cacheKey])
  return objectUrl
}

// Read-only view of a confirmed profile's construction, shown wherever the
// Observation stage needs to confirm the diagram matches the real cable
// (Scientist and Scientific Assistant both see the same rendering).
export function ProfileSummaryCard(
  { profile, coresTested, sampleId }: { profile: CableProfile; coresTested: number; sampleId?: string },
) {
  const diagramSrc = useAuthenticatedImage(profile.hand_drawn_diagram_url, sampleId ? `${sampleId}:diagram` : undefined)
  return (
    <Paper withBorder radius="md" p="md">
      <Group justify="space-between" mb="sm">
        <Text fw={700}>Cable Construction</Text>
        <Group gap={6}>
          {profile.conductor_material && <Badge variant="light" size="sm">{profile.conductor_material}</Badge>}
          {profile.insulation_material && <Badge variant="light" size="sm">{profile.insulation_material} {profile.insulation_type}</Badge>}
          {profile.sheath_type && <Badge variant="light" size="sm">Sheath {profile.sheath_type}</Badge>}
          {profile.cable_shape && <Badge variant="light" size="sm" color="gray">{profile.cable_shape}</Badge>}
        </Group>
      </Group>
      {(profile.overall_diameter_mm != null || profile.diameter_under_sheath_mm != null) && (
        <Group gap="lg" mb="sm">
          {profile.overall_diameter_mm != null && (
            <Text size="xs" c="dimmed">OD (Overall Diameter): <b>{profile.overall_diameter_mm} mm</b></Text>
          )}
          {profile.diameter_under_sheath_mm != null && (
            <Text size="xs" c="dimmed">ID (Under Sheath): <b>{profile.diameter_under_sheath_mm} mm</b></Text>
          )}
        </Group>
      )}
      {profile.hand_drawn_diagram_url ? (
        <Stack gap={4}>
          <Text size="xs" c="dimmed">Custom diagram uploaded (construction doesn't fit the standard parametric model).</Text>
          {diagramSrc ? (
            <Image src={diagramSrc} radius="md" mah={320} fit="contain" />
          ) : (
            <Center h={160}><Loader size="sm" /></Center>
          )}
        </Stack>
      ) : (
        <CableDiagram
          coresTested={coresTested}
          coreColors={profile.tested_core_colors ?? []}
          conductorMaterial={profile.conductor_material}
          insulationType={profile.insulation_type}
          insulationMaterial={profile.insulation_material}
          hasInnerSheath={!!profile.has_inner_sheath}
          hasArmour={!!profile.has_armour}
          armourType={profile.armour_type}
          armourMaterial={profile.armour_material}
          armourStrandCount={profile.armour_strand_count}
          hasOuterSheath={!!profile.has_outer_sheath}
          sheathType={profile.sheath_type}
        />
      )}
    </Paper>
  )
}
