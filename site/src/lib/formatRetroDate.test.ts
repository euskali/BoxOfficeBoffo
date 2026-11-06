import { describe, expect, it } from 'vitest'
import { formatRetroDate } from './formatRetroDate'

describe('formatRetroDate', () => {
  it('formats in the retro style', () => {
    expect(formatRetroDate(new Date('2026-11-05T12:00:00Z'))).toBe('Thu Nov 5 2026')
  })
  it('uses UTC and does not pad the day', () => {
    expect(formatRetroDate(new Date('2026-01-01T00:00:00Z'))).toBe('Thu Jan 1 2026')
    expect(formatRetroDate(new Date('2026-12-31T23:59:59Z'))).toBe('Thu Dec 31 2026')
  })
})
