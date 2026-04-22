'use client'

import { useRouter } from 'next/navigation'
import { Select } from '@/components/ui/select'

const timeRanges = [
  { value: '1', label: 'Last 24 hours' },
  { value: '7', label: 'Last 7 days' },
  { value: '14', label: 'Last 14 days' },
  { value: '30', label: 'Last 30 days' },
]

export function CostsRangeSelector({ days }: { days: number }) {
  const router = useRouter()

  return (
    <Select
      value={days.toString()}
      onChange={(e) => {
        const value = e.target.value
        router.push(`/costs?days=${value}`)
      }}
      className="w-48"
    >
      {timeRanges.map((range) => (
        <option key={range.value} value={range.value}>
          {range.label}
        </option>
      ))}
    </Select>
  )
}
