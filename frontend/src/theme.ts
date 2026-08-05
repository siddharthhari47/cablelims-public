import { createTheme, type MantineColorsTuple } from '@mantine/core'

// Navy/accent palette matched to the Test Report_694.docx template
// (backend/app/services/docx_report_filler.py) so the on-screen product and
// the generated report feel like the same system.
const navy: MantineColorsTuple = [
  '#eef2fb', '#dbe4f5', '#b3c5e8', '#89a5da', '#6690d0', '#4f7fc9',
  '#4278c8', '#3468b1', '#2a5a9d', '#1b3f78',
]

const brandAccent: MantineColorsTuple = [
  '#eaf1ff', '#d3e2ff', '#a6c4ff', '#75a4ff', '#4d89fd', '#3576f7',
  '#2769e6', '#1a58cf', '#0f4bb8', '#0b2447',
]

export const theme = createTheme({
  primaryColor: 'brandAccent',
  colors: {
    navy,
    brandAccent,
  },
  fontFamily: 'Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
  headings: {
    fontFamily: 'Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
    fontWeight: '650',
  },
  defaultRadius: 'md',
  components: {
    Card: {
      defaultProps: { radius: 'lg', withBorder: true },
    },
    Button: {
      defaultProps: { radius: 'md' },
    },
  },
})
