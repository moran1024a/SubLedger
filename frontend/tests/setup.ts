import { config } from '@vue/test-utils'

const elementComponents = [
  'el-alert',
  'el-button',
  'el-card',
  'el-date-picker',
  'el-descriptions',
  'el-descriptions-item',
  'el-dialog',
  'el-divider',
  'el-drawer',
  'el-empty',
  'el-form',
  'el-form-item',
  'el-input',
  'el-input-number',
  'el-option',
  'el-pagination',
  'el-radio-button',
  'el-radio-group',
  'el-result',
  'el-select',
  'el-switch',
  'el-table',
  'el-table-column',
  'el-tag',
  'el-time-picker',
]

config.global.stubs = Object.fromEntries(elementComponents.map((name) => [name, true]))
config.global.directives = { loading: () => {} }
