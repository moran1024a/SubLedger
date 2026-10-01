export const timezones = Array.from(
  new Set([
    'UTC',
    'Asia/Shanghai',
    'Asia/Singapore',
    'Asia/Tokyo',
    'Europe/London',
    'America/New_York',
    'America/Los_Angeles',
    ...(typeof Intl.supportedValuesOf === 'function' ? Intl.supportedValuesOf('timeZone') : []),
  ]),
)
export const currencies = ['CNY', 'USD', 'EUR', 'GBP', 'JPY', 'SGD', 'HKD']
