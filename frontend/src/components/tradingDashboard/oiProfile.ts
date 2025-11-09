import type { StrikeSeriesLine, StrikeValuePoint } from '../../hooks/useFoAnalytics'

const normalizeBucket = (value?: string | null): string | null => {
  if (!value) return null
  return value.trim().toUpperCase()
}

const computeStrikeGap = (points: StrikeValuePoint[]): number => {
  if (points.length < 2) return 0
  const ordered = Array.from(new Set(points.map((point) => point.strike))).sort((a, b) => a - b)
  let minGap = Infinity
  for (let index = 1; index < ordered.length; index += 1) {
    const diff = ordered[index] - ordered[index - 1]
    if (diff > 0 && diff < minGap) {
      minGap = diff
    }
  }
  return Number.isFinite(minGap) ? minGap : 0
}

const resolveMoneynessBucket = (
  point: StrikeValuePoint,
  atmStrike: number | null,
  strikeGap: number,
  side: 'call' | 'put',
): string => {
  if (atmStrike == null || !Number.isFinite(atmStrike) || strikeGap <= 0) {
    return 'ATM'
  }
  const diff = point.strike - atmStrike
  if (Math.abs(diff) <= strikeGap * 0.6) {
    return 'ATM'
  }
  const steps = Math.max(1, Math.round(Math.abs(diff) / strikeGap))
  const bucket = diff >= 0 ? `OTM${steps}` : `ITM${steps}`
  if (side === 'put') {
    return diff <= 0 ? `OTM${steps}` : `ITM${steps}`
  }
  return bucket
}

export interface OiProfile {
  perStrike: Array<{ strike: number; callOi: number; putOi: number }>
  perExpiry: Array<{
    label: string
    color: string
    callOi: number
    putOi: number
    callOiChange: number
    putOiChange: number
    pcr?: number | null
    maxPain?: number | null
  }>
  totals: { callOi: number; putOi: number; callOiChange: number; putOiChange: number }
}

export const buildOiProfile = (
  lines: StrikeSeriesLine[],
  expiryFilter: string[],
  moneynessFilter: string[],
): OiProfile => {
  const expirySet = new Set(expiryFilter)
  const moneynessSet = new Set(moneynessFilter?.map((bucket) => bucket.toUpperCase()))
  const perStrikeMap = new Map<
    number,
    { strike: number; callOi: number; putOi: number }
  >()
  const perExpiryMap = new Map<
    string,
    {
      label: string
      color: string
      callOi: number
      putOi: number
      callOiChange: number
      putOiChange: number
      pcr?: number | null
      maxPain?: number | null
    }
  >()

  const shouldIncludeExpiry = (line: StrikeSeriesLine) =>
    !expirySet.size || expirySet.has(line.expiry)

  const shouldIncludeBucket = (
    point: StrikeValuePoint,
    atmStrike: number | null,
    strikeGap: number,
    side: 'call' | 'put',
  ) => {
    if (!moneynessSet.size) return true
    const rawBucket =
      normalizeBucket(point.source?.moneyness_bucket) ??
      normalizeBucket(point.source?.moneyness)
    const bucket =
      rawBucket ?? resolveMoneynessBucket(point, atmStrike, strikeGap, side)
    return moneynessSet.has(bucket)
  }

  lines.forEach((line) => {
    if (!shouldIncludeExpiry(line)) return
    const summary =
      perExpiryMap.get(line.expiry) ??
      perExpiryMap.set(line.expiry, {
        label: line.label ?? line.expiry,
        color: line.color,
        callOi: 0,
        putOi: 0,
        callOiChange: 0,
        putOiChange: 0,
        pcr: line.metadata?.pcr ?? null,
        maxPain: line.metadata?.max_pain_strike ?? null,
      }).get(line.expiry)!

    const strikeGap = computeStrikeGap([...line.calls, ...line.puts])
    const atmReference = line.metadata?.atm_strike ?? null

    line.calls.forEach((point) => {
      if (!shouldIncludeBucket(point, atmReference, strikeGap, 'call')) return
      const oi = point.source?.oi ?? point.value ?? 0
      const oiChange = point.source?.oi_change ?? 0
      if (!perStrikeMap.has(point.strike)) {
        perStrikeMap.set(point.strike, { strike: point.strike, callOi: 0, putOi: 0 })
      }
      perStrikeMap.get(point.strike)!.callOi += oi
      summary.callOi += oi
      summary.callOiChange += oiChange
    })

    line.puts.forEach((point) => {
      if (!shouldIncludeBucket(point, atmReference, strikeGap, 'put')) return
      const oi = point.source?.oi ?? point.value ?? 0
      const oiChange = point.source?.oi_change ?? 0
      if (!perStrikeMap.has(point.strike)) {
        perStrikeMap.set(point.strike, { strike: point.strike, callOi: 0, putOi: 0 })
      }
      perStrikeMap.get(point.strike)!.putOi += oi
      summary.putOi += oi
      summary.putOiChange += oiChange
    })
  })

  const perStrike = Array.from(perStrikeMap.values())
    .filter((entry) => entry.callOi > 0 || entry.putOi > 0)
    .sort((a, b) => b.strike - a.strike)

  const perExpiry = Array.from(perExpiryMap.values()).filter(
    (entry) => entry.callOi > 0 || entry.putOi > 0,
  )

  const totals = perExpiry.reduce(
    (acc, entry) => ({
      callOi: acc.callOi + entry.callOi,
      putOi: acc.putOi + entry.putOi,
      callOiChange: acc.callOiChange + entry.callOiChange,
      putOiChange: acc.putOiChange + entry.putOiChange,
    }),
    { callOi: 0, putOi: 0, callOiChange: 0, putOiChange: 0 },
  )

  return { perStrike, perExpiry, totals }
}

