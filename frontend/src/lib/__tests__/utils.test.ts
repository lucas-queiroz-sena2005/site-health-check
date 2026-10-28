import { describe, it, expect } from 'vitest'
import { extractApiErrorMessage } from '../utils'

describe('extractApiErrorMessage', () => {
  it('extracts string detail from FastAPI error response', async () => {
    const res = {
      json: async () => ({ detail: 'Targets cannot be empty' }),
    } as unknown as Response

    const msg = await extractApiErrorMessage(res, 'Fallback error')
    expect(msg).toBe('Targets cannot be empty')
  })

  it('extracts and cleans Pydantic 422 validation error arrays into human language', async () => {
    const res = {
      json: async () => ({
        detail: [
          {
            loc: ['body', 'cron_expression'],
            msg: "Value error, Invalid cron expression format (expected 5 fields, e.g. '0 0 * * *')",
            type: 'value_error',
          },
        ],
      }),
    } as unknown as Response

    const msg = await extractApiErrorMessage(res, 'Fallback error')
    expect(msg).toBe("Invalid cron expression format (expected 5 fields, e.g. '0 0 * * *')")
  })

  it('returns fallback message when response body is not valid JSON', async () => {
    const res = {
      json: async () => {
        throw new Error('Invalid JSON')
      },
    } as unknown as Response

    const msg = await extractApiErrorMessage(res, 'Failed to create scan')
    expect(msg).toBe('Failed to create scan')
  })
})
