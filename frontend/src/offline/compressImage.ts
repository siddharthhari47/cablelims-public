const MAX_DIMENSION = 1600
const JPEG_QUALITY = 0.82

// Applied unconditionally (online or offline), not just while queued --
// today's raw phone photo (often several MB) has zero client-side
// compression anywhere in this app; the backend re-encodes to its own JPEG
// quality setting anyway (see image_upload.py's settings.upload_jpeg_quality,
// default 85), so there's no value preserving more resolution/bitrate than
// that. Faster uploads on a normal connection too, not just a smaller
// footprint sitting in IndexedDB while offline.
export async function compressImage(file: File): Promise<File> {
  const bitmap = await createImageBitmap(file).catch(() => null)
  if (!bitmap) return file // not a decodable image (shouldn't happen -- <input accept="image/*"> already filters) -- fail open, let the server's own validation handle it

  const scale = Math.min(1, MAX_DIMENSION / Math.max(bitmap.width, bitmap.height))
  const width = Math.round(bitmap.width * scale)
  const height = Math.round(bitmap.height * scale)

  const canvas = document.createElement('canvas')
  canvas.width = width
  canvas.height = height
  const ctx = canvas.getContext('2d')
  if (!ctx) return file
  ctx.drawImage(bitmap, 0, 0, width, height)
  bitmap.close()

  const blob = await new Promise<Blob | null>((resolve) => canvas.toBlob(resolve, 'image/jpeg', JPEG_QUALITY))
  if (!blob) return file

  // Re-encoding always strips EXIF (GPS, device identifiers) as a side
  // effect of the canvas round-trip, same reasoning as image_upload.py's
  // own server-side re-encode -- a real, if incidental, privacy improvement.
  const name = file.name.replace(/\.[^.]+$/, '') + '.jpg'
  return new File([blob], name, { type: 'image/jpeg' })
}
