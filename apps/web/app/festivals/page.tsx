'use client'

import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { getFestivals, bulkResearchFestivals } from '@/lib/api'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Select } from '@/components/ui/select'
import { getStateColor, getStateLabel, formatRelativeTime } from '@/lib/utils'
import Link from 'next/link'
import { Search, RefreshCw, PlayCircle } from 'lucide-react'
import type { FestivalState } from '@/types'

const states: FestivalState[] = [
  'discovered',
  'researching',
  'researched',
  'syncing',
  'synced',
  'failed',
  'skipped',
  'needs_review',
]

export default function FestivalsPage() {
  const [search, setSearch] = useState('')
  const [state, setState] = useState('')
  const [offset, setOffset] = useState(0)
  const [bulkResult, setBulkResult] = useState<any>(null)
  const limit = 20
  const queryClient = useQueryClient()

  const { data, isLoading, refetch } = useQuery({
    queryKey: ['festivals', { search, state, offset, limit }],
    queryFn: () =>
      getFestivals({
        search: search || undefined,
        state: state || undefined,
        offset,
        limit,
      }),
  })

  const bulkResearchMutation = useMutation({
    mutationFn: bulkResearchFestivals,
    onSuccess: (result) => {
      setBulkResult(result)
      queryClient.invalidateQueries({ queryKey: ['festivals'] })
      queryClient.invalidateQueries({ queryKey: ['stats'] })
      
      // Clear result after 5 seconds
      setTimeout(() => setBulkResult(null), 5000)
    },
  })

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault()
    setOffset(0)
    refetch()
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-3xl font-bold">Festivals</h1>
        <div className="flex gap-2">
          <Button 
            onClick={() => bulkResearchMutation.mutate({ failure_reason: 'dates', limit: 50 })}
            disabled={bulkResearchMutation.isPending}
            variant="outline"
            size="sm"
          >
            <PlayCircle className="h-4 w-4 mr-2" />
            Bulk Research Failed (Dates)
          </Button>
          <Button onClick={() => refetch()} variant="outline" size="sm">
            <RefreshCw className="h-4 w-4 mr-2" />
            Refresh
          </Button>
        </div>
      </div>

      {/* Bulk Research Result */}
      {bulkResult && (
        <Card className="border-green-500">
          <CardContent className="pt-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="font-medium text-green-700">{bulkResult.message}</p>
                <p className="text-sm text-muted-foreground">
                  Queued: {bulkResult.queued} | Matched: {bulkResult.total_matched} | 
                  Daily used: {bulkResult.daily_used}/50 | Remaining: {bulkResult.daily_remaining}
                </p>
              </div>
              <Button 
                variant="ghost" 
                size="sm" 
                onClick={() => setBulkResult(null)}
              >
                Dismiss
              </Button>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Filters */}
      <Card>
        <CardContent className="pt-6">
          <form onSubmit={handleSearch} className="flex gap-4">
            <div className="flex-1">
              <Input
                placeholder="Search festivals..."
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                className="w-full"
              />
            </div>
            <Select
              value={state}
              onChange={(e) => {
                setState(e.target.value)
                setOffset(0)
              }}
              className="w-48"
            >
              <option value="">All States</option>
              {states.map((s) => (
                <option key={s} value={s}>
                  {getStateLabel(s)}
                </option>
              ))}
            </Select>
            <Button type="submit">
              <Search className="h-4 w-4 mr-2" />
              Search
            </Button>
          </form>
        </CardContent>
      </Card>

      {/* Results */}
      <Card>
        <CardHeader>
          <CardTitle>
            {data ? `${data.total} Festivals` : 'Loading...'}
          </CardTitle>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <div className="text-center py-8 text-muted-foreground">
              Loading...
            </div>
          ) : data?.festivals.length === 0 ? (
            <div className="text-center py-8 text-muted-foreground">
              No festivals found
            </div>
          ) : (
            <div className="space-y-2">
              {data?.festivals.map((festival) => (
                <Link
                  key={festival.id}
                  href={`/festivals/${festival.id}`}
                  className="flex items-center justify-between rounded-lg border p-4 hover:bg-muted transition-colors"
                >
                  <div className="flex items-center gap-4">
                    <div
                      className={`w-3 h-3 rounded-full ${getStateColor(
                        festival.state
                      )}`}
                    />
                    <div>
                      <p className="font-medium">{festival.name}</p>
                      <p className="text-sm text-muted-foreground">
                        Source: {festival.source} •{' '}
                        {formatRelativeTime(festival.created_at)}
                      </p>
                    </div>
                  </div>
                  <div className="flex items-center gap-4">
                    {festival.retry_count > 0 && (
                      <Badge variant="destructive">
                        {festival.retry_count} retries
                      </Badge>
                    )}
                    <Badge
                      variant="secondary"
                      className={`${getStateColor(festival.state)} text-white`}
                    >
                      {getStateLabel(festival.state)}
                    </Badge>
                  </div>
                </Link>
              ))}
            </div>
          )}

          {/* Pagination */}
          {data && data.total > limit && (
            <div className="flex items-center justify-between mt-6">
              <Button
                variant="outline"
                disabled={offset === 0}
                onClick={() => setOffset(Math.max(0, offset - limit))}
              >
                Previous
              </Button>
              <span className="text-sm text-muted-foreground">
                Page {Math.floor(offset / limit) + 1} of{' '}
                {Math.ceil(data.total / limit)}
              </span>
              <Button
                variant="outline"
                disabled={offset + limit >= data.total}
                onClick={() => setOffset(offset + limit)}
              >
                Next
              </Button>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
