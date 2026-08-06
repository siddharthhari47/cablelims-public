export interface UserBrief {
  id: string
  full_name: string
  username: string
  role: string
}

export interface Standard {
  standard_id: string
  name: string
  edition?: string
  amendment?: string
  scope_summary?: string
}

export type CorePosition = 'RED' | 'YELLOW' | 'BLUE' | 'BLACK' | 'SHEATH' | null

export type ArmourType = 'Steel Wire' | 'Steel Strip' | 'Steel Tape' | 'Aluminium Wire'

export interface CableProfile {
  conductor_material?: string
  conductor_class?: string
  insulation_type?: string   // "A" | "C" | "D" per IS 5831 -- drives engineering limits
  insulation_material?: string // "PVC" | "XLPE" | "PE" -- descriptive/diagram label
  sheath_type?: string       // "ST1" | "ST2" | "ST3"
  fire_category?: string
  construction?: string
  marking_image_path?: boolean
  source?: string
  confirmed?: boolean
  // Explicit per-core colour assignment, one entry per tested core in
  // physical position order. Never auto-assigned -- always a deliberate
  // choice made during profiling.
  tested_core_colors?: string[] | null
  has_outer_sheath?: boolean
  has_armour?: boolean
  has_inner_sheath?: boolean
  armour_type?: ArmourType | null
  armour_material?: string | null
  armour_strand_count?: number | null
  hand_drawn_diagram_url?: string | null
  cable_shape?: 'Round' | 'Flat'
  // Round only (IS 694 Table 5-7) -- a diameter isn't meaningful for a flat
  // cross-section.
  overall_diameter_mm?: number | null
  diameter_under_sheath_mm?: number | null
  // Flat only (IS 694 cl.22, Table 10 -- "Overall Dimensions, Max (W x H)").
  flat_width_mm?: number | null
  flat_height_mm?: number | null
}

export interface SampleSummary {
  applicable_tests: number
  completed_tests: number
  passed: number
  failed: number
  undetermined: number
  repeat_required: string[]
  overall_confidence_pct: number | null
  overall_status: string
}

export interface SampleListItem {
  sample_id: string
  status: string
  standard: string | null
  cores: number
  cores_tested: number | null
  csa_mm2: number
  created_at: string
  registered_by: UserBrief | null
  assigned_assistant: UserBrief | null
  profile: CableProfile | null
  // The Scientist's explanation from the most recent RETURN, if the review
  // cycle it belongs to hasn't been approved yet.
  last_review_comment: string | null
  summary: SampleSummary
}

export interface InputField {
  key: string
  label: string
  type: 'number' | 'boolean' | 'number_array' | 'select'
  unit?: string
  count?: number
  default?: number
  options?: string[]
}

export interface LatestResult {
  attempt_number: number
  raw_values: Record<string, unknown>
  calculated_value: number | null
  calculated_unit: string | null
  limit_value: number | null
  limit_operator: string | null
  margin_pct: number | null
  confidence_state: string
  result: string
  effective_result: string
  explanation: string
  limit_source_kind: string
  limit_source_ref: string | null
  submitted_by: UserBrief
  submitted_at: string
  performed_by_role: string | null
  overridden: boolean
  override_result: string | null
  override_limit_value: number | null
  override_reason: string | null
  overridden_by: UserBrief | null
  overridden_at: string | null
  verified: boolean
  verified_by: UserBrief | null
  verified_at: string | null
}

export type ReportSection = 'CONDUCTOR' | 'DIMENSIONAL' | 'PHYSICAL' | 'COMPLETED_CABLE'

export interface AssignedTestDetail {
  assigned_test_id: string
  test_id: string
  name: string
  category: string
  unit: string
  input_schema: InputField[]
  report_section: ReportSection | null
  clause_reference: string | null
  procedure_summary: string | null
  procedure_measurement: string | null
  procedure_formula: string | null
  core_position: CorePosition
  mandatory: boolean
  enabled: boolean
  status: string
  attempts: number
  latest_result: LatestResult | null
}

export interface SampleDetail {
  sample_id: string
  status: string
  product_family: string
  standard: Standard | null
  cores: number
  cores_tested: number | null
  csa_mm2: number
  remarks: string | null
  last_review_comment: string | null
  locked: boolean
  registered_by: UserBrief | null
  assigned_assistant: UserBrief | null
  created_at: string
  profile: CableProfile | null
  tests: AssignedTestDetail[]
  summary: SampleSummary
  certificate: { certificate_no: string; overall_decision: string; generated_at: string } | null
  // UI pre-fill suggestion only -- never applied automatically.
  suggested_core_colors: string[] | null
}

export interface DashboardData {
  total_samples: number
  pending: number
  in_progress: number
  scientist_review: number
  completed: number
  repeat_tests: number
  certificates_issued: number
  recent_activity: { actor: string; action: string; entity_type: string; entity_id: string; timestamp: string }[]
}
