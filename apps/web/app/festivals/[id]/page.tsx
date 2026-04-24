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
  validateFestival,
  getJobActivity,
} from '@/lib/api'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { TagList } from '@/components/agents/TagBadge'
import { Button } from '@/components/ui/button'
import {
  getStateColor,
  getStateLabel,
  formatDate,
  formatCurrency,
  getPartyMapUrl,
  formatRelativeTime,
} from '@/lib/utils'
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
  DollarSign,
  Calendar,
  Users,
  MapPin,
  Ticket,
  ShieldCheck,
  ShieldAlert,
  ClipboardCheck,
  Loader2,
  Activity,
  Copy,
  Check,
  Edit,
} from 'lucide-react'
import { Separator } from '@/components/ui/separator'
import type { FestivalState } from '@/types'
import type { JobActivityItem } from '@/lib/api'
import dynamic from 'next/dynamic'
import { useToast } from '@/components/ui/toast-provider'

const AgentStreamViewer = dynamic(
  () => import('@/components/AgentStreamViewer').then((mod) => mod.AgentStreamViewer),
  { ssr: false }
)
import { StateBadge } from '@/components/state-badge'
import { ConfirmDialog, PromptDialog } from '@/components/ui/dialog-confirm'
import { SkeletonCard } from '@/components/ui/skeleton'
import { FestivalEditor } from '@/components/FestivalEditor'
import { ValidationPanel } from '@/components/ValidationPanel'

export default function FestivalDetailPage() {
  const params = useParams()
  const id = params.id as string
  const queryClient = useQueryClient()
  const [actionError, setActionError] = useState<string | null>(null)
  const { success, error: toastError } = useToast()

  // Dialog states
  const [skipDialogOpen, setSkipDialogOpen] = useState(false)
  const [resetDialogOpen, setResetDialogOpen] = useState(false)
  const [forceSyncDialogOpen, setForceSyncDialogOpen] = useState(false)
  const [editDialogOpen, setEditDialogOpen] = useState(false)

  const { data: festival, isLoading } = useQuery({
    queryKey: ['festival', id],
    queryFn: () => getFestival(id),
  })

  const { data: activity } = useQuery({
    queryKey: ['job-activity', id, 20],
    queryFn: () => getJobActivity(undefined, 20),
    refetchInterval: 10000,
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
    onError: (err: Error) => setActionError(err.message),
  })

  const researchMutation = useMutation({
    mutationFn: () => researchFestival(id),
    onSuccess: () => {
      invalidateFestival()
      success('Research started')
    },
    onError: (err: Error) => setActionError(err.message),
  })

  const syncMutation = useMutation({
    mutationFn: () => syncFestival(id),
    onSuccess: () => {
      invalidateFestival()
      success('Sync started')
    },
    onError: (err: Error) => setActionError(err.message),
  })

  const skipMutation = useMutation({
    mutationFn: (reason: string) => skipFestival(id, reason),
    onSuccess: () => {
      invalidateFestival()
      success('Festival skipped')
    },
    onError: (err: Error) => setActionError(err.message),
  })

  const retryMutation = useMutation({
    mutationFn: () => retryFestival(id),
    onSuccess: () => {
      invalidateFestival()
      success('Retry started')
    },
    onError: (err: Error) => setActionError(err.message),
  })

  const resetMutation = useMutation({
    mutationFn: (targetState: FestivalState) => resetFestival(id, targetState),
    onSuccess: () => {
      invalidateFestival()
      success('Festival reset')
    },
    onError: (err: Error) => setActionError(err.message),
  })

  const forceSyncMutation = useMutation({
    mutationFn: () => forceSyncFestival(id),
    onSuccess: () => {
      invalidateFestival()
      success('Force sync started')
    },
    onError: (err: Error) => setActionError(err.message),
  })

  const validateMutation = useMutation({
    mutationFn: () => validateFestival(id),
    onSuccess: (data) => {
      invalidateFestival()
      const v = data.validation
      if (v.is_valid) {
        success(`Validation passed — ${Math.round(v.completeness_score * 100)}% complete`)
      } else {
        toastError(
          `Validation failed — ${v.errors.length} error(s), ${v.warnings.length} warning(s)`
        )
      }
    },
    onError: (err: Error) => setActionError(err.message),
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
        <div className="space-y-6">
          <SkeletonCard className="h-16" />
          <div className="grid gap-6 md:grid-cols-2">
            <SkeletonCard className="h-64" />
            <SkeletonCard className="h-64" />
          </div>
        </div>
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

    // Edit action for festivals that can be manually edited
    if (
      festival.state === 'researched_partial' ||
      festival.state === 'researched' ||
      festival.state === 'validation_failed' ||
      festival.state === 'needs_review'
    ) {
      actions.push({
        label: 'Edit',
        icon: Edit,
        onClick: () => setEditDialogOpen(true),
        loading: false,
        variant: 'default' as const,
      })
    }

    // Always available
    actions.push(
      {
        label: 'Validate',
        icon: ClipboardCheck,
        onClick: () => validateMutation.mutate(),
        loading: validateMutation.isPending,
        variant: 'outline' as const,
      },
      {
        label: 'Skip',
        icon: SkipForward,
        onClick: () => setSkipDialogOpen(true),
        loading: skipMutation.isPending,
        variant: 'outline' as const,
      },
      {
        label: 'Reset to Discovered',
        icon: AlertTriangle,
        onClick: () => setResetDialogOpen(true),
        loading: resetMutation.isPending,
        variant: 'outline' as const,
      }
    )

    if (festival.state === 'synced') {
      actions.push({
        label: 'Force Re-sync',
        icon: Upload,
        onClick: () => setForceSyncDialogOpen(true),
        loading: forceSyncMutation.isPending,
        variant: 'outline' as const,
      })
    }

    return actions
  }

  const actions = getAvailableActions()

  // Filter activity items for this festival
  const festivalActivity =
    activity?.items.filter(
      (item: JobActivityItem) => item.festival_id === id
    ) || []

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
                    {researchData.festival_data.name && (
                      <li>Name: {researchData.festival_data.name}</li>
                    )}
                    {researchData.festival_data.description && (
                      <li>
                        Description:{' '}
                        {researchData.festival_data.description.substring(0, 100)}...
                      </li>
                    )}
                    {researchData.festival_data.url && (
                      <li>
                        URL:{' '}
                        <a
                          href={researchData.festival_data.url}
                          className="text-blue-600 hover:underline"
                          target="_blank"
                          rel="noopener noreferrer"
                        >
                          {researchData.festival_data.url}
                        </a>
                      </li>
                    )}
                    {researchData.festival_data.logo && <li>Logo URL provided</li>}
                    {researchData.festival_data.date_time && (
                      <li>
                        Dates: {researchData.festival_data.date_time.start} to{' '}
                        {researchData.festival_data.date_time.end}
                      </li>
                    )}
                    {researchData.festival_data.tags && (
                      <li className="list-none mt-2">
                        <TagList tags={researchData.festival_data.tags} />
                      </li>
                    )}
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
              <span className="font-medium">
                Research failed: {failure.reason}
              </span>
            </div>
            <div className="text-sm">
              <p className="text-red-600">{failure.message}</p>
              {failure.completeness_score > 0 && (
                <div className="mt-3">
                  <p className="font-medium mb-1">
                    Progress: {Math.round(failure.completeness_score * 100)}% complete
                  </p>
                  <div className="w-full bg-gray-200 rounded-full h-2.5">
                    <div
                      className="bg-yellow-500 h-2.5 rounded-full"
                      style={{ width: `${failure.completeness_score * 100}%` }}
                    ></div>
                  </div>
                </div>
              )}
              {failure.collected_partial_data &&
                Object.keys(failure.collected_partial_data).length > 0 && (
                  <div className="mt-3">
                    <p className="font-medium mb-1">Partial data collected:</p>
                    <div className="bg-yellow-50 p-3 rounded border border-yellow-200 text-sm">
                      <pre className="whitespace-pre-wrap">
                        {JSON.stringify(failure.collected_partial_data, null, 2)}
                      </pre>
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
            <span className="font-medium">
              Research failed: {festival.failure_reason}
            </span>
          </div>
          {festival.failure_message && (
            <p className="text-sm text-red-600">{festival.failure_message}</p>
          )}
          {festival.research_completeness_score !== undefined &&
            festival.research_completeness_score > 0 && (
              <div className="mt-2">
                <p className="text-sm font-medium">
                  Completeness: {Math.round(festival.research_completeness_score * 100)}%
                </p>
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
        <StateBadge state={festival.state} className="text-sm px-3 py-1" />
      </div>

      <h1 className="text-2xl sm:text-3xl font-bold break-words">
        {festival.name}
      </h1>

      {actionError && (
        <div className="rounded-lg border border-destructive bg-destructive/10 p-4 text-destructive">
          {actionError}
        </div>
      )}

      {/* Status Badges Row */}
      <div className="flex flex-wrap gap-2">
        {festival.is_duplicate && (
          <Badge variant="destructive" className="gap-1">
            <Copy className="h-3 w-3" /> Duplicate
          </Badge>
        )}
        {festival.is_new_event_date && (
          <Badge variant="secondary" className="gap-1">
            <Calendar className="h-3 w-3" /> New Date
          </Badge>
        )}
        {festival.date_confirmed ? (
          <Badge variant="default" className="bg-green-500 gap-1">
            <Check className="h-3 w-3" /> Date Confirmed
          </Badge>
        ) : (
          <Badge variant="outline" className="gap-1">
            <AlertTriangle className="h-3 w-3" /> Unconfirmed
          </Badge>
        )}
        {festival.research_completeness_score !== undefined && (
          <Badge
            variant={
              festival.research_completeness_score >= 0.8
                ? 'default'
                : festival.research_completeness_score >= 0.5
                  ? 'secondary'
                  : 'destructive'
            }
            className={
              festival.research_completeness_score >= 0.8 ? 'bg-green-500' : ''
            }
          >
            {Math.round(festival.research_completeness_score * 100)}% Complete
          </Badge>
        )}
      </div>

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
                  <Icon
                    className={`h-4 w-4 ${action.loading ? 'animate-spin' : ''}`}
                  />
                  {action.label}
                </Button>
              )
            })}
          </div>
        </CardContent>
      </Card>

      {/* Details + Integration + Costs */}
      <div className="grid gap-6 md:grid-cols-3">
        <Card>
          <CardHeader>
            <CardTitle>Basic Info</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-2 sm:gap-4 text-sm">
              <div className="text-muted-foreground sm:text-right">ID</div>
              <div className="sm:col-span-2 font-mono text-xs break-all">
                {festival.id}
              </div>

              <div className="text-muted-foreground sm:text-right">Source</div>
              <div className="sm:col-span-2">{festival.source}</div>

              <div className="text-muted-foreground sm:text-right">
                Retry Count
              </div>
              <div className="sm:col-span-2">{festival.retry_count}</div>

              <div className="text-muted-foreground sm:text-right">Created</div>
              <div className="sm:col-span-2">
                {formatDate(festival.created_at)}
              </div>

              <div className="text-muted-foreground sm:text-right">Updated</div>
              <div className="sm:col-span-2">
                {formatDate(festival.updated_at)}
              </div>
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
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-2 sm:gap-4 text-sm">
                  <div className="text-muted-foreground sm:text-right">
                    Event ID
                  </div>
                  <div className="sm:col-span-2 font-mono text-xs break-all">
                    <a
                      href={
                        getPartyMapUrl(
                          festival.partymap_event_id,
                          festival.partymap_date_id
                        ) || undefined
                      }
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-blue-600 hover:underline inline-flex items-center gap-1"
                    >
                      {festival.partymap_event_id}
                      <ExternalLink className="h-3 w-3" />
                    </a>
                  </div>

                  {festival.partymap_date_id && (
                    <>
                      <div className="text-muted-foreground sm:text-right">
                        Date ID
                      </div>
                      <div className="sm:col-span-2 font-mono text-xs break-all">
                        <a
                          href={
                            getPartyMapUrl(
                              festival.partymap_event_id,
                              festival.partymap_date_id
                            ) || undefined
                          }
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-blue-600 hover:underline inline-flex items-center gap-1"
                        >
                          {festival.partymap_date_id}
                          <ExternalLink className="h-3 w-3" />
                        </a>
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

        {/* Costs Card */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <DollarSign className="h-5 w-5 text-amber-500" />
              Costs
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="flex items-center justify-between text-sm">
              <span className="text-muted-foreground">Discovery</span>
              <span className="font-medium">
                {formatCurrency(festival.discovery_cost_cents ?? 0)}
              </span>
            </div>
            <div className="flex items-center justify-between text-sm">
              <span className="text-muted-foreground">Research</span>
              <span className="font-medium">
                {formatCurrency(festival.research_cost_cents ?? 0)}
              </span>
            </div>
            <Separator />
            <div className="flex items-center justify-between text-sm font-semibold">
              <span>Total</span>
              <span>{formatCurrency(festival.total_cost_cents ?? 0)}</span>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Event Dates */}
      {festival.event_dates && festival.event_dates.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Calendar className="h-5 w-5 text-muted-foreground" />
              Event Dates
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
            {festival.event_dates.map((ed: any, idx: number) => (
              <Card key={ed.id || idx}>
                <CardHeader className="pb-3">
                  <CardTitle className="text-base flex items-center gap-2">
                    <Calendar className="h-4 w-4 text-muted-foreground" />
                    {ed.start_date
                      ? new Date(ed.start_date).toLocaleDateString()
                      : 'TBD'}
                    {ed.end_date && ed.end_date !== ed.start_date && (
                      <span className="text-muted-foreground font-normal">
                        {' '}
                        — {new Date(ed.end_date).toLocaleDateString()}
                      </span>
                    )}
                  </CardTitle>
                </CardHeader>
                <CardContent className="space-y-3 text-sm">
                  {ed.venue && (
                    <div className="flex items-start gap-2">
                      <MapPin className="h-4 w-4 text-muted-foreground mt-0.5 flex-shrink-0" />
                      <span>{ed.venue}</span>
                    </div>
                  )}
                  {ed.location && (
                    <div className="flex items-start gap-2">
                      <MapPin className="h-4 w-4 text-muted-foreground mt-0.5 flex-shrink-0" />
                      <span>{ed.location}</span>
                    </div>
                  )}
                  {ed.lineup && ed.lineup.length > 0 && (
                    <div className="flex items-start gap-2">
                      <Users className="h-4 w-4 text-muted-foreground mt-0.5 flex-shrink-0" />
                      <span className="truncate">
                        {ed.lineup.slice(0, 5).join(', ')}
                        {ed.lineup.length > 5 && ` +${ed.lineup.length - 5} more`}
                      </span>
                    </div>
                  )}
                  {ed.ticket_url && (
                    <a
                      href={ed.ticket_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="flex items-center gap-2 text-primary hover:underline"
                    >
                      <Ticket className="h-4 w-4" />
                      Tickets
                    </a>
                  )}
                  {ed.price_info && (
                    <div className="flex items-start gap-2">
                      <DollarSign className="h-4 w-4 text-muted-foreground mt-0.5 flex-shrink-0" />
                      <span>{ed.price_info}</span>
                    </div>
                  )}
                  {ed.size_estimate && (
                    <Badge variant="outline">{ed.size_estimate}</Badge>
                  )}
                </CardContent>
              </Card>
            ))}
          </div>
          </CardContent>
        </Card>
      )}

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
                  variant={festival.research_data.success ? 'default' : 'destructive'}
                  className={festival.research_data.success ? 'bg-green-500' : ''}
                >
                  {festival.research_data.success ? '✓ Success' : '✗ Failed'}
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

      {/* Validation Panel */}
      <ValidationPanel
        festival={festival as any}
        onValidate={() => validateMutation.mutate()}
        isLoading={validateMutation.isPending}
      />

      {/* Pipeline Activity History */}
      {festivalActivity.length > 0 && (
        <Card>
          <CardHeader className="flex flex-row items-center justify-between">
            <CardTitle className="flex items-center gap-2">
              <Activity className="h-5 w-5 text-muted-foreground" />
              Pipeline History
            </CardTitle>
            <Badge variant="outline">{festivalActivity.length} events</Badge>
          </CardHeader>
          <CardContent>
            <div className="space-y-2">
              {festivalActivity.map((item: JobActivityItem) => (
                <div
                  key={item.id}
                  className="flex items-center justify-between rounded-lg border p-3"
                >
                  <div className="flex items-center gap-3 min-w-0">
                    <Badge variant="outline" className="capitalize flex-shrink-0">
                      {item.job_type}
                    </Badge>
                    <div className="min-w-0">
                      <p className="text-sm font-medium truncate">
                        {item.message}
                      </p>
                      <p className="text-xs text-muted-foreground capitalize">
                        {item.activity_type}
                      </p>
                    </div>
                  </div>
                  <span className="text-xs text-muted-foreground flex-shrink-0 ml-2">
                    {formatRelativeTime(item.created_at)}
                  </span>
                </div>
              ))}
            </div>
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

      {/* Dialogs */}
      <PromptDialog
        open={skipDialogOpen}
        title="Skip Festival"
        description="Please provide a reason for skipping this festival."
        placeholder="Reason for skipping..."
        confirmLabel="Skip"
        onConfirm={(reason) => {
          skipMutation.mutate(reason)
          setSkipDialogOpen(false)
        }}
        onCancel={() => setSkipDialogOpen(false)}
      />

      <ConfirmDialog
        open={resetDialogOpen}
        title="Reset Festival"
        description="Reset to discovered state? This will clear research data."
        confirmLabel="Reset"
        variant="destructive"
        onConfirm={() => {
          resetMutation.mutate('discovered')
          setResetDialogOpen(false)
        }}
        onCancel={() => setResetDialogOpen(false)}
      />

      <ConfirmDialog
        open={forceSyncDialogOpen}
        title="Force Re-sync"
        description="Are you sure you want to force sync this festival?"
        confirmLabel="Force Sync"
        onConfirm={() => {
          forceSyncMutation.mutate()
          setForceSyncDialogOpen(false)
        }}
        onCancel={() => setForceSyncDialogOpen(false)}
      />

      {/* Festival Editor Dialog */}
      <FestivalEditor
        festivalId={id}
        festivalName={festival.name}
        initialData={festival.research_data}
        currentState={festival.state}
        open={editDialogOpen}
        onOpenChange={setEditDialogOpen}
      />
    </div>
  )
}
