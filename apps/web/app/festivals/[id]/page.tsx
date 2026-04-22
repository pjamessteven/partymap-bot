'use client'

import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useParams } from 'next/navigation'
import {
  getFestival,
  deduplicateFestival,
  researchFestival,
  syncFestival,
  skipFestival,
  retryFestival,
  resetFestival,
  forceSyncFestival,
} from '@/lib/api'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { getStateColor, getStateLabel, formatDate, formatCurrency } from '@/lib/utils'
import Link from 'next/link'
import {
  ArrowLeft,
  CheckCircle,
  XCircle,
  RotateCcw,
  Search,
  Upload,
  SkipForward,
  AlertTriangle,
  ExternalLink,
} from 'lucide-react'
import type { FestivalState } from '@/types'
import { AgentStreamViewer } from '@/components/AgentStreamViewer'
import { useToast } from '@/components/ui/toast-provider'

export default function FestivalDetailPage() {
  const params = useParams()
  const id = params.id as string
  const queryClient = useQueryClient()
  const [actionError, setActionError] = useState<string | null>(null)
  const { success, error: toastError } = useToast()

  const { data: festival, isLoading } = useQuery({
    queryKey: ['festival', id],
    queryFn: () => getFestival(id),
  })

  const invalidateFestival = () => {
    queryClient.invalidateQueries({ queryKey: ['festival', id] })
    queryClient.invalidateQueries({ queryKey: ['festivals'] })
    queryClient.invalidateQueries({ queryKey: ['stats'] })
  }

  const dedupMutation = useMutation({
    mutationFn: () => deduplicateFestival(id),
    onSuccess: () => {
      invalidateFestival()
      success('Deduplication started')
    },
    onError: (err: Error) => {
      setActionError(err.message)
      toastError('Deduplication failed')
    },
  })

  const researchMutation = useMutation({
    mutationFn: () => researchFestival(id),
    onSuccess: () => {
      invalidateFestival()
      success('Research started')
    },
    onError: (err: Error) => {
      setActionError(err.message)
      toastError('Research failed')
    },
  })

  const syncMutation = useMutation({
    mutationFn: () => syncFestival(id),
    onSuccess: () => {
      invalidateFestival()
      success('Sync started')
    },
    onError: (err: Error) => {
      setActionError(err.message)
      toastError('Sync failed')
    },
  })

  const skipMutation = useMutation({
    mutationFn: (reason: string) => skipFestival(id, reason),
    onSuccess: () => {
      invalidateFestival()
      success('Festival skipped')
    },
    onError: (err: Error) => {
      setActionError(err.message)
      toastError('Skip failed')
    },
  })

  const retryMutation = useMutation({
    mutationFn: () => retryFestival(id),
    onSuccess: () => {
      invalidateFestival()
      success('Retry started')
    },
    onError: (err: Error) => {
      setActionError(err.message)
      toastError('Retry failed')
    },
  })

  const resetMutation = useMutation({
    mutationFn: (targetState: FestivalState) => resetFestival(id, targetState),
    onSuccess: () => {
      invalidateFestival()
      success('Festival reset')
    },
    onError: (err: Error) => {
      setActionError(err.message)
      toastError('Reset failed')
    },
  })

  const forceSyncMutation = useMutation({
    mutationFn: () => forceSyncFestival(id),
    onSuccess: () => {
      invalidateFestival()
      success('Force sync started')
    },
    onError: (err: Error) => {
      setActionError(err.message)
      toastError('Force sync failed')
    },
  })

  if (isLoading) {
    return (
      <div className="space-y-6">
        <Link href="/festivals">
          <Button variant="ghost" size="sm">
            <ArrowLeft className="h-4 w-4 mr-2" />
            Back to Festivals
          </Button>
        </Link>
        <div className="text-center py-8">Loading...</div>
      </div>
    )
  }

  if (!festival) {
    return (
      <div className="space-y-6">
        <Link href="/festivals">
          <Button variant="ghost" size="sm">
            <ArrowLeft className="h-4 w-4 mr-2" />
            Back to Festivals
          </Button>
        </Link>
        <div className="text-center py-8 text-destructive">Festival not found</div>
      </div>
    )
  }

  const getAvailableActions = () => {
    const actions = []

    if (festival.state === 'discovered') {
      actions.push({
        label: 'Deduplicate',
        icon: Search,
        onClick: () => dedupMutation.mutate(),
        loading: dedupMutation.isPending,
        variant: 'default' as const,
      })
    }

    if (festival.state === 'researching') {
      actions.push({
        label: 'Research',
        icon: RotateCcw,
        onClick: () => researchMutation.mutate(),
        loading: researchMutation.isPending,
        variant: 'default' as const,
      })
    }

    if (festival.state === 'researched') {
      actions.push({
        label: 'Sync',
        icon: Upload,
        onClick: () => syncMutation.mutate(),
        loading: syncMutation.isPending,
        variant: 'default' as const,
      })
    }

    if (festival.state === 'failed') {
      actions.push({
        label: 'Retry',
        icon: RotateCcw,
        onClick: () => retryMutation.mutate(),
        loading: retryMutation.isPending,
        variant: 'default' as const,
      })
    }

    // Always available
    actions.push(
      {
        label: 'Skip',
        icon: SkipForward,
        onClick: () => {
          const reason = window.prompt('Reason for skipping:')
          if (reason) skipMutation.mutate(reason)
        },
        loading: skipMutation.isPending,
        variant: 'outline' as const,
      },
      {
        label: 'Reset to Discovered',
        icon: AlertTriangle,
        onClick: () => {
          if (window.confirm('Reset to discovered state? This will clear research data.')) {
            resetMutation.mutate('discovered')
          }
        },
        loading: resetMutation.isPending,
        variant: 'outline' as const,
      }
    )

    if (festival.state === 'synced') {
      actions.push({
        label: 'Force Re-sync',
        icon: Upload,
        onClick: () => {
          if (window.confirm('Force sync this festival?')) {
            forceSyncMutation.mutate()
          }
        },
        loading: forceSyncMutation.isPending,
        variant: 'outline' as const,
      })
    }

    return actions
  }

  const actions = getAvailableActions()

  // Function to render research outcome summary
  const renderResearchOutcome = (researchData: Record<string, any>) => {
    // Check if this is a structured ResearchResult
    if (researchData.success !== undefined) {
      if (researchData.success) {
        // Successful research
        return (
          <div className="space-y-3">
            <div className="flex items-center text-green-600">
              <CheckCircle className="h-5 w-5 mr-2" />
              <span className="font-medium">Research completed successfully</span>
            </div>
            <div className="text-sm">
              <p>All required fields were found and validated.</p>
              {researchData.festival_data && (
                <div className="mt-2 text-sm bg-green-50 p-3 rounded border border-green-200">
                  <p className="font-medium">Collected data:</p>
                  <ul className="list-disc pl-5 mt-1 space-y-1">
                    {researchData.festival_data.name && <li>Name: {researchData.festival_data.name}</li>}
                    {researchData.festival_data.description && <li>Description: {researchData.festival_data.description.substring(0, 100)}...</li>}
                    {researchData.festival_data.url && <li>URL: <a href={researchData.festival_data.url} className="text-blue-600 hover:underline" target="_blank" rel="noopener noreferrer">{researchData.festival_data.url}</a></li>}
                    {researchData.festival_data.logo && <li>Logo URL provided</li>}
                    {researchData.festival_data.date_time && <li>Dates: {researchData.festival_data.date_time.start} to {researchData.festival_data.date_time.end}</li>}
                    {researchData.festival_data.tags && <li>Tags: {researchData.festival_data.tags.join(', ')}</li>}
                  </ul>
                </div>
              )}
            </div>
          </div>
        )
      } else if (researchData.failure) {
        // Failed research
        const failure = researchData.failure
        return (
          <div className="space-y-3">
            <div className="flex items-center text-red-600">
              <XCircle className="h-5 w-5 mr-2" />
              <span className="font-medium">Research failed: {failure.reason}</span>
            </div>
            <div className="text-sm">
              <p className="text-red-600">{failure.message}</p>
              {failure.completeness_score > 0 && (
                <div className="mt-3">
                  <p className="font-medium mb-1">Progress: {Math.round(failure.completeness_score * 100)}% complete</p>
                  <div className="w-full bg-gray-200 rounded-full h-2.5">
                    <div 
                      className="bg-yellow-500 h-2.5 rounded-full" 
                      style={{ width: `${failure.completeness_score * 100}%` }}
                    ></div>
                  </div>
                </div>
              )}
              {failure.collected_partial_data && Object.keys(failure.collected_partial_data).length > 0 && (
                <div className="mt-3">
                  <p className="font-medium mb-1">Partial data collected:</p>
                  <div className="bg-yellow-50 p-3 rounded border border-yellow-200 text-sm">
                    <pre className="whitespace-pre-wrap">{JSON.stringify(failure.collected_partial_data, null, 2)}</pre>
                  </div>
                </div>
              )}
              {failure.missing_fields && failure.missing_fields.length > 0 && (
                <div className="mt-3">
                  <p className="font-medium mb-1">Missing required fields:</p>
                  <ul className="list-disc pl-5 text-red-600">
                    {failure.missing_fields.map((field: string, idx: number) => (
                      <li key={idx}>{field}</li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          </div>
        )
      }
    }
    
    // Legacy format or raw data - fallback to showing the structure
    if (festival.failure_reason) {
      return (
        <div className="space-y-2">
          <div className="flex items-center text-red-600">
            <XCircle className="h-5 w-5 mr-2" />
            <span className="font-medium">Research failed: {festival.failure_reason}</span>
          </div>
          {festival.failure_message && (
            <p className="text-sm text-red-600">{festival.failure_message}</p>
          )}
          {festival.research_completeness_score !== undefined && festival.research_completeness_score > 0 && (
            <div className="mt-2">
              <p className="text-sm font-medium">Completeness: {Math.round(festival.research_completeness_score * 100)}%</p>
            </div>
          )}
        </div>
      )
    }
    
    // Unknown format - show raw data
    return (
      <div className="text-sm text-muted-foreground">
        <p>Research data available (legacy format).</p>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <Link href="/festivals">
          <Button variant="ghost" size="sm">
            <ArrowLeft className="h-4 w-4 mr-2" />
            Back to Festivals
          </Button>
        </Link>
        <Badge
          variant="secondary"
          className={`${getStateColor(festival.state)} text-white text-sm px-3 py-1`}
        >
          {getStateLabel(festival.state)}
        </Badge>
      </div>

      <h1 className="text-3xl font-bold">{festival.name}</h1>

      {actionError && (
        <div className="rounded-lg border border-destructive bg-destructive/10 p-4 text-destructive">
          {actionError}
        </div>
      )}

      {/* Actions */}
      <Card>
        <CardHeader>
          <CardTitle>Actions</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex flex-wrap gap-2">
            {actions.map((action) => {
              const Icon = action.icon
              return (
                <Button
                  key={action.label}
                  onClick={action.onClick}
                  disabled={action.loading}
                  variant={action.variant}
                  className="gap-2"
                >
                  <Icon className={`h-4 w-4 ${action.loading ? 'animate-spin' : ''}`} />
                  {action.label}
                </Button>
              )
            })}
          </div>
        </CardContent>
      </Card>

      {/* Details */}
      <div className="grid gap-6 md:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Basic Info</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid grid-cols-3 gap-4 text-sm">
              <div className="text-muted-foreground">ID</div>
              <div className="col-span-2 font-mono text-xs">{festival.id}</div>

              <div className="text-muted-foreground">Source</div>
              <div className="col-span-2">{festival.source}</div>

              <div className="text-muted-foreground">Retry Count</div>
              <div className="col-span-2">{festival.retry_count}</div>

              <div className="text-muted-foreground">Created</div>
              <div className="col-span-2">{formatDate(festival.created_at)}</div>

              <div className="text-muted-foreground">Updated</div>
              <div className="col-span-2">{formatDate(festival.updated_at)}</div>
            </div>

            {festival.source_url && (
              <a
                href={festival.source_url}
                target="_blank"
                rel="noopener noreferrer"
                className="flex items-center gap-2 text-primary hover:underline"
              >
                <ExternalLink className="h-4 w-4" />
                View Source
              </a>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>PartyMap Integration</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            {festival.partymap_event_id ? (
              <>
                <div className="grid grid-cols-3 gap-4 text-sm">
                  <div className="text-muted-foreground">Event ID</div>
                  <div className="col-span-2 font-mono text-xs">
                    {festival.partymap_event_id}
                  </div>

                  {festival.partymap_date_id && (
                    <>
                      <div className="text-muted-foreground">Date ID</div>
                      <div className="col-span-2 font-mono text-xs">
                        {festival.partymap_date_id}
                      </div>
                    </>
                  )}
                </div>
                <div className="flex items-center gap-2 text-green-600">
                  <CheckCircle className="h-4 w-4" />
                  <span className="text-sm">Synced to PartyMap</span>
                </div>
              </>
            ) : (
              <div className="flex items-center gap-2 text-muted-foreground">
                <XCircle className="h-4 w-4" />
                <span className="text-sm">Not yet synced</span>
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Last Error */}
      {festival.last_error && (
        <Card className="border-destructive">
          <CardHeader>
            <CardTitle className="text-destructive flex items-center gap-2">
              <AlertTriangle className="h-5 w-5" />
              Last Error
            </CardTitle>
          </CardHeader>
          <CardContent>
            <pre className="bg-muted p-4 rounded-lg text-sm overflow-auto">
              {festival.last_error}
            </pre>
          </CardContent>
        </Card>
      )}

      {/* Discovered Data */}
      {festival.discovered_data && Object.keys(festival.discovered_data).length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>Discovered Data</CardTitle>
          </CardHeader>
          <CardContent>
            <pre className="bg-muted p-4 rounded-lg text-sm overflow-auto max-h-96">
              {JSON.stringify(festival.discovered_data, null, 2)}
            </pre>
          </CardContent>
        </Card>
      )}

      {/* Research Data */}
      {festival.research_data && Object.keys(festival.research_data).length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center justify-between">
              <span>Research Outcome</span>
              {festival.research_data.success !== undefined && (
                <Badge 
                  variant={festival.research_data.success ? "default" : "destructive"}
                  className={festival.research_data.success ? "bg-green-500" : ""}
                >
                  {festival.research_data.success ? "✓ Success" : "✗ Failed"}
                </Badge>
              )}
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            {/* Show simplified outcome summary */}
            {renderResearchOutcome(festival.research_data)}
            
            {/* Expandable detailed view */}
            <details className="mt-4">
              <summary className="cursor-pointer text-sm font-medium text-muted-foreground hover:text-foreground">
                View raw research data
              </summary>
              <pre className="bg-muted p-4 rounded-lg text-sm overflow-auto max-h-96 mt-2">
                {JSON.stringify(festival.research_data, null, 2)}
              </pre>
            </details>
          </CardContent>
        </Card>
      )}

      {/* Agent Stream - Show when researching or researched */}
      {(festival.state === 'researching' || festival.state === 'researched') && (
        <Card>
          <CardHeader>
            <CardTitle>Agent Stream</CardTitle>
          </CardHeader>
          <CardContent>
            <AgentStreamViewer
              festivalId={id}
              threadId={festival.current_thread_id}
              onComplete={invalidateFestival}
            />
          </CardContent>
        </Card>
      )}
    </div>
  )
}
