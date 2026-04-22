'use client'

import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { getPendingFestivals, deduplicateFestival, researchFestival, syncFestival } from '@/lib/api'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Select } from '@/components/ui/select'
import { getStateColor, getStateLabel, getActionLabel, formatRelativeTime, getPartyMapUrl } from '@/lib/utils'
import Link from 'next/link'
import { RefreshCw, Search, RotateCcw, Upload, ExternalLink, Inbox } from 'lucide-react'
import type { FestivalState, FestivalAction } from '@/types'
import { useToast } from '@/components/ui/toast-provider'
import { StateBadge } from '@/components/state-badge'
import { EmptyState } from '@/components/empty-state'

const states: FestivalState[] = [
  'discovered',
  'researching',
  'researched',
  'failed',
]

export default function PendingPage() {
  const [state, setState] = useState('')
  const queryClient = useQueryClient()
  const { success, error } = useToast()

  const { data: pending, isLoading, refetch } = useQuery({
    queryKey: ['pending', state],
    queryFn: () => getPendingFestivals(state || undefined, 50),
  })

  const invalidateAll = () => {
    queryClient.invalidateQueries({ queryKey: ['pending'] })
    queryClient.invalidateQueries({ queryKey: ['festivals'] })
    queryClient.invalidateQueries({ queryKey: ['stats'] })
  }

  const dedupMutation = useMutation({
    mutationFn: (id: string) => deduplicateFestival(id),
    onSuccess: () => {
      invalidateAll()
      success('Deduplication started')
    },
  })

  const researchMutation = useMutation({
    mutationFn: (id: string) => researchFestival(id),
    onSuccess: () => {
      invalidateAll()
      success('Research started')
    },
  })

  const syncMutation = useMutation({
    mutationFn: (id: string) => syncFestival(id),
    onSuccess: () => {
      invalidateAll()
      success('Sync started')
    },
  })

  const handleAction = (festivalId: string, action: FestivalAction) => {
    if (action === 'deduplicate') {
      dedupMutation.mutate(festivalId)
    } else if (action === 'research') {
      researchMutation.mutate(festivalId)
    } else if (action === 'sync') {
      syncMutation.mutate(festivalId)
    }
  }

  const getActionIcon = (action: FestivalAction) => {
    switch (action) {
      case 'deduplicate':
        return Search
      case 'research':
        return RotateCcw
      case 'sync':
        return Upload
      default:
        return ExternalLink
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-3xl font-bold">Pending Actions</h1>
        <Button onClick={() => refetch()} variant="outline" size="sm">
          <RefreshCw className="h-4 w-4 mr-2" />
          Refresh
        </Button>
      </div>

      {/* Filter */}
      <Card>
        <CardContent className="pt-6">
          <div className="flex items-center gap-4">
            <span className="text-sm font-medium">Filter by state:</span>
            <Select
              value={state}
              onChange={(e) => setState(e.target.value)}
              className="w-48"
            >
              <option value="">All Pending</option>
              {states.map((s) => (
                <option key={s} value={s}>
                  {getStateLabel(s)}
                </option>
              ))}
            </Select>
          </div>
        </CardContent>
      </Card>

      {/* Pending List */}
      <Card>
        <CardHeader>
          <CardTitle>
            {isLoading
              ? 'Loading...'
              : `${pending?.length ?? 0} Pending Actions`}
          </CardTitle>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <div className="text-center py-8 text-muted-foreground">
              Loading...
            </div>
          ) : pending?.length === 0 ? (
            <EmptyState
              icon={Inbox}
              title="No pending actions"
              description="All caught up! New festivals requiring action will appear here."
            />
          ) : (
            <div className="space-y-2">
              {pending?.map((item) => {
                const ActionIcon = getActionIcon(item.suggested_action)
                const isProcessing =
                  dedupMutation.variables === item.festival_id &&
                  dedupMutation.isPending

                return (
                  <div
                    key={item.festival_id}
                    className="flex items-center justify-between rounded-lg border p-4"
                  >
                    <div className="flex items-center gap-4">
                      <StateBadge state={item.state} className="hidden sm:inline-flex" />
                      <div className={`w-3 h-3 rounded-full ${getStateColor(item.state)} sm:hidden`} />
                      <div>
                        <Link
                          href={`/festivals/${item.festival_id}`}
                          className="font-medium hover:text-primary"
                        >
                          {item.name}
                        </Link>
                        <p className="text-sm text-muted-foreground">
                          Source: {item.source} •{' '}
                          {formatRelativeTime(item.created_at)}
                          {item.retry_count > 0 &&
                            ` • ${item.retry_count} retries`}
                        </p>
                      </div>
                    </div>
                    <div className="flex items-center gap-2 sm:gap-3">
                      {item.partymap_event_id && (
                        <a
                          href={getPartyMapUrl(item.partymap_event_id) || undefined}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="inline-flex items-center gap-1 rounded-full bg-green-100 px-2 py-0.5 text-xs font-medium text-green-700 hover:bg-green-200 dark:bg-green-900 dark:text-green-200"
                          onClick={(e) => e.stopPropagation()}
                        >
                          <ExternalLink className="h-3 w-3" />
                          PartyMap
                        </a>
                      )}
                      <Badge variant="outline" className="hidden sm:inline-flex">
                        {getActionLabel(item.suggested_action)}
                      </Badge>
                      <Button
                        size="sm"
                        onClick={() =>
                          handleAction(item.festival_id, item.suggested_action)
                        }
                        disabled={
                          (dedupMutation.isPending &&
                            dedupMutation.variables === item.festival_id) ||
                          (researchMutation.isPending &&
                            researchMutation.variables === item.festival_id) ||
                          (syncMutation.isPending &&
                            syncMutation.variables === item.festival_id)
                        }
                      >
                        <ActionIcon
                          className={`h-4 w-4 mr-2 ${
                            isProcessing ? 'animate-spin' : ''
                          }`}
                        />
                        {getActionLabel(item.suggested_action)}
                      </Button>
                      <Link href={`/festivals/${item.festival_id}`}>
                        <Button variant="ghost" size="sm" aria-label="View festival details">
                          <ExternalLink className="h-4 w-4" />
                        </Button>
                      </Link>
                    </div>
                  </div>
                )
              })}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
