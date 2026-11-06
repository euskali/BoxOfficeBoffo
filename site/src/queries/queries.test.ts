import { describe, expect, it } from 'vitest'
import { helloSql } from './index'

describe('queries', () => {
  it('exposes hello.sql as raw text', () => {
    expect(helloSql).toContain('SELECT 1999')
  })
})
