'use client'

import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { getCosts } from '@/lib/api'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Select } from '@/components/ui/select'
import { formatCurrency, formatDate } from '@/lib/utils'

const timeRanges = [
  { value: '1', label: 'Last 24 hours' },
  { value: '7', label: 'Last 7 days' },
  { value: '14', label: 'Last 14 days' },
  { value: '30', label: 'Last 30 days' },
]

export default function CostsPage() {
  const [days, setDays] = useState(7)

  const { data: costs, isLoading } = useQuery({
    queryKey: ['costs', days],
    queryFn: () => getCosts(days),
  })

  const totalCost = costs?.reduce((sum, cost) => sum + cost.cost_cents, 0) ?? 0

  const costsByAgent = costs?.reduce((acc, cost) => {
    if (!acc[cost.agent_type]) acc[cost.agent_type] = 0
    acc[cost.agent_type] += cost.cost_cents
    return acc
  }, {} as Record<string, number>)

  const costsByOperation = costs?.reduce((acc, cost) => {
    if (!acc[cost.operation]) acc[cost.operation] = 0
    acc[cost.operation] += cost.cost_cents
    return acc
  }, {} as Record<string, number>)

  if (isLoading) {
    return (
      <div className="space-y-6">
        <h1 className="text-3xl font-bold">Cost Tracking</h1>
        <div className="text-center py-8">Loading...</div>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-3xl font-bold">Cost Tracking</h1>
        <Select
          value={days.toString()}
          onChange={(e) => setDays(parseInt(e.target.value))}
          className="w-48"
        >
          {timeRanges.map((range) => (
            <option key={range.value} value={range.value}>
              {range.label}
            </option>
          ))}
        </Select>
      </div>

      {/* Summary Cards */}
      <div className="grid gap-4 md:grid-cols-3">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Total Cost</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{formatCurrency(totalCost)}</div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Total Operations</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{costs?.length ?? 0}</div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Average per Operation</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              {formatCurrency(costs?.length ? totalCost / costs.length : 0)}
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Costs by Agent */}
      {costsByAgent && Object.keys(costsByAgent).length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>Costs by Agent</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex flex-wrap gap-2">
              {Object.entries(costsByAgent).map(([agent, cost]) => (
                <Badge key={agent} variant="secondary" className="text-sm px-3 py-1">
                  {agent}: {formatCurrency(cost)}
                </Badge>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Costs by Operation */}
      {costsByOperation && Object.keys(costsByOperation).length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>Costs by Operation</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex flex-wrap gap-2">
              {Object.entries(costsByOperation).map(([operation, cost]) => (
                <Badge key={operation} variant="secondary" className="text-sm px-3 py-1">
                  {operation}: {formatCurrency(cost)}
                </Badge>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Recent Costs */}
      <Card>
        <CardHeader>
          <CardTitle>Recent Operations</CardTitle>
        </CardHeader>
        <CardContent>
          {costs && costs.length > 0 ? (
            <div className="space-y-2">
              {costs.slice(0, 50).map((cost) => (
                <div
                  key={cost.id}
                  className="flex items-center justify-between rounded-lg border p-3"
                >
                  <div className="flex items-center gap-4">
                    <Badge variant="outline">{cost.agent_type}</Badge>
                    <span className="font-medium">{cost.operation}</span>
                    {cost.festival_id && (
                      <span className="text-xs text-muted-foreground font-mono">
                        {cost.festival_id.slice(0, 8)}...
                      </span>
                    )}
                  </div>
                  <div className="flex items-center gap-4 text-sm">
                    <span className="font-mono">
                      {formatCurrency(cost.cost_cents)}
                    </span>
                    <span className="text-muted-foreground">
                      {formatDate(cost.created_at)}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-muted-foreground text-center py-4">
              No cost data for this period
            </p>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
