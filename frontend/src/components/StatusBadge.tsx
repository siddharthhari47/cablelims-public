import { Badge } from '@mantine/core'

const STATUS_COLOR: Record<string, string> = {
  REGISTERED: 'gray',
  PROFILE_PENDING: 'yellow',
  PROFILE_VERIFIED: 'blue',
  TESTING: 'blue',
  REPEAT_REQUIRED: 'orange',
  SCIENTIST_REVIEW: 'grape',
  APPROVED: 'green',
  REPORT_GENERATED: 'teal',
  ARCHIVED: 'dark',
  PASS: 'green',
  FAIL: 'red',
  UNDETERMINED: 'orange',
  MANUAL_REVIEW_APPROVED: 'grape',
  PENDING: 'gray',
  COMPLETED: 'green',
  IN_PROGRESS: 'blue',
  VERIFIED: 'green',
  PLACEHOLDER: 'yellow',
  MISSING: 'red',
  AWAITING_TEST_ASSIGNMENT: 'gray',
  TESTING_IN_PROGRESS: 'blue',
  UNDER_SCIENTIST_REVIEW: 'grape',
  READY_FOR_APPROVAL: 'teal',
}

const STATUS_LABEL: Record<string, string> = {
  UNDER_SCIENTIST_REVIEW: 'UNDER SCIENTIST REVIEW',
  TESTING_IN_PROGRESS: 'TESTING IN PROGRESS',
  READY_FOR_APPROVAL: 'READY FOR APPROVAL',
  AWAITING_TEST_ASSIGNMENT: 'AWAITING PROFILE',
}

export function StatusBadge({ status, size = 'md' }: { status: string; size?: string }) {
  const color = STATUS_COLOR[status] ?? 'gray'
  const label = STATUS_LABEL[status] ?? status.replace(/_/g, ' ')
  return (
    <Badge color={color} variant="light" size={size} radius="sm">
      {label}
    </Badge>
  )
}
