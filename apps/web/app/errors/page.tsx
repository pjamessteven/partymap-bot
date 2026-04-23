'use client'

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  getErrorStats,
  getQuarantinedFestivals,
  retryQuarantinedFestival,
  bulkRetryQuarantined,
  cleanupExpiredQuarantined,
  getCircuitBreakerStatus,
  resetCircuitBreaker,
} from '@/lib/api'
import { ErrorDashboard } from '@/components/ErrorDashboard'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { AlertTriangle, RefreshCw } from 'lucide-react'
import { cn } from '@/lib/utils'
import type { FestivalWithValidation, FestivalState } from '@/types'

export default function ErrorsPage() {
  const queryClient = useQueryClient()

  const {
    data: stats,
    isLoading: statsLoading,
    refetch: refetchStats,
  } = useQuery({
    queryKey: ['error-stats'],
    queryFn: getErrorStats,
  })

  const {
    data: quarantined,
    isLoading: quarantinedLoading,
    refetch: refetchQuarantined,
  } = useQuery({
    queryKey: ['quarantined-festivals'],
    queryFn: () => getQuarantinedFestivals({ limit: 50 }),
  })

  const {
    data: circuitBreakers,
    isLoading: cbLoading,
    refetch: refetchCB,
  } = useQuery({
    queryKey: ['circuit-breakers'],
    queryFn: getCircuitBreakerStatus,
  })

  const retryMutation = useMutation({
    mutationFn: (festivalId: string) => retryQuarantinedFestival(festivalId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['quarantined-festivals'] })
      queryClient.invalidateQueries({ queryKey: ['error-stats'] })
      queryClient.invalidateQueries({ queryKey: ['festivals'] })
    },
  })

  const bulkRetryMutation = useMutation({
    mutationFn: (festivalIds: string[]) => bulkRetryQuarantined(festivalIds),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['quarantined-festivals'] })
      queryClient.invalidateQueries({ queryKey: ['error-stats'] })
      queryClient.invalidateQueries({ queryKey: ['festivals'] })
    },
  })

  const cleanupMutation = useMutation({
    mutationFn: cleanupExpiredQuarantined,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['quarantined-festivals'] })
      queryClient.invalidateQueries({ queryKey: ['error-stats'] })
    },
  })

  const resetCBMutation = useMutation({
    mutationFn: resetCircuitBreaker,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['circuit-breakers'] })
    },
  })

  const isLoading = statsLoading || quarantinedLoading || cbLoading

  const refreshAll = () => {
    refetchStats()
    refetchQuarantined()
    refetchCB()
  }

  const allQuarantinedIds = quarantined?.items.map((item: any) => item.id) || []

  if (isLoading) {
    return (
      <div className="space-y-6">
        <div className="flex items-center justify-between">
          <h1 className="text-2xl sm:text-3xl font-bold">Error Dashboard</h1>
        </div>
        <Card>
          <CardContent className="pt-6">
            <div className="text-center py-12 text-muted-foreground">
              Loading error data...
            </div>
          </CardContent>
        </Card>
      </div>
    )
  }

  // Transform quarantined festivals to match ErrorDashboard props
  const recentErrors: FestivalWithValidation[] = quarantined?.items.map((item: any) => ({
    id: item.id,
    name: item.name,
    source: item.source,
    state: 'quarantined' as FestivalState,
    retry_count: item.retry_count,
    error_category: item.error_category,
    quarantined_at: item.quarantined_at,
    quarantine_reason: item.quarantine_reason,
    validation_status: item.validation_status,
    validation_errors: [],
    validation_warnings: [],
    max_retries_reached: true,
    created_at: item.quarantined_at || '',
    updated_at: item.quarantined_at || '',
  })) || []

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <AlertTriangle className="h-8 w-8 text-red-500" />
          <h1 className="text-2xl sm:text-3xl font-bold">Error Dashboard</h1>
        </div>
        <div className="flex items-center gap-2">
          {allQuarantinedIds.length > 0 && (
            <Button
              onClick={() => bulkRetryMutation.mutate(allQuarantinedIds)}
              disabled={bulkRetryMutation.isPending}
              variant="outline"
              size="sm"
            >
              <RefreshCw className={cn('h-4 w-4 mr-2', bulkRetryMutation.isPending && 'animate-spin')} />
              Retry All ({allQuarantinedIds.length})
            </Button>
          )}
          <Button onClick={refreshAll} variant="outline" size="sm">
            <RefreshCw className="h-4 w-4 mr-2" />
            Refresh
          </Button>
        </div>
      </div>

      {stats && quarantined && circuitBreakers && (
        <ErrorDashboard
          dlqStats={stats.dlq}
          circuitBreakers={circuitBreakers.breakers}
          recentErrors={recentErrors}
          onRetry={(id) => retryMutation.mutate(id)}
          onBulkRetry={(ids) => bulkRetryMutation.mutate(ids)}
          onCleanup={() => cleanupMutation.mutate()}
        />
      )}

      {/* Circuit Breaker Manual Controls */}
      <Card>
        <CardHeader>
          <CardTitle>Circuit Breaker Controls</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex flex-wrap gap-2">
            {Object.entries(circuitBreakers?.breakers || {}).map(([name, metrics]: [string, any]) => (
              <div key={name} className="flex items-center gap-2">
                <span className="text-sm font-medium capitalize">{name}:</span>
                <span
                  className={`text-xs px-2 py-1 rounded-full border ${
                    metrics.state === 'open'
                      ? 'border-red-500 text-red-600 bg-red-50 dark:bg-red-950/20'
                      : metrics.state === 'half_open'
                      ? 'border-yellow-500 text-yellow-600 bg-yellow-50 dark:bg-yellow-950/20'
                      : 'border-green-500 text-green-600 bg-green-50 dark:bg-green-950/20'
                  }`}
                >
                  {metrics.state}
                </span>
                {metrics.state !== 'closed' && (
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => resetCBMutation.mutate(name)}
                    disabled={resetCBMutation.isPending}
                  >
                    Reset
                  </Button>
                )}
              </div>
            ))}
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
