'use client'

import { useState, useMemo } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  getFestivals,
  bulkResearchFestivals,
  deduplicateFestival,
  researchFestival,
  syncFestival,
  skipFestival,
  retryFestival,
  resetFestival,
} from '@/lib/api'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Select } from '@/components/ui/select'
import { Checkbox } from '@/components/ui/checkbox'
import {
  getStateColor,
  getStateLabel,
  getStateDescription,
  formatRelativeTime,
  getPartyMapUrl,
} from '@/lib/utils'
import Link from 'next/link'
import {
  Search,
  RefreshCw,
  PlayCircle,
  ArrowUpDown,
  Music,
  ExternalLink,
  RotateCcw,
  Upload,
  SkipForward,
  AlertTriangle,
  Search as SearchIcon,
  X,
  CheckSquare,
  Square,
  Edit,
  Plus,
  Info,
} from 'lucide-react'
import type { FestivalState } from '@/types'
import { ValidationBadge, RetryCountBadge } from '@/components/ValidationBadge'
import { TagList, extractTagsFromResearchData } from '@/components/agents/TagBadge'
import { StateBadge } from '@/components/state-badge'
import { EmptyState } from '@/components/empty-state'
import { SkeletonList } from '@/components/ui/skeleton'
import { ConfirmDialog, PromptDialog } from '@/components/ui/dialog-confirm'
import { useToast } from '@/components/ui/toast-provider'
import { FestivalEditor } from '@/components/FestivalEditor'

// Grouped states with descriptions for better UX
const stateGroups = [
  {
    label: 'Discovery',
    states: [
      { value: 'discovered', label: 'Discovered', description: 'Newly discovered, awaiting deduplication' },
    ],
  },
  {
    label: 'Workflow',
    states: [
      { value: 'needs_research_new', label: 'Needs Research (New)', description: 'New festival ready for research' },
      { value: 'needs_research_update', label: 'Needs Research (Update)', description: 'Existing event needing update' },
    ],
  },
  {
    label: 'Research',
    states: [
      { value: 'researching', label: 'Researching', description: 'Research agent is actively working' },
      { value: 'researched', label: 'Researched', description: 'Complete data ready for sync' },
      { value: 'researched_partial', label: 'Researched (Partial)', description: 'Missing logo - needs manual edit' },
    ],
  },
  {
    label: 'Sync',
    states: [
      { value: 'syncing', label: 'Syncing', description: 'Currently syncing to PartyMap' },
      { value: 'synced', label: 'Synced', description: 'Successfully synced to PartyMap' },
    ],
  },
  {
    label: 'Validation',
    states: [
      { value: 'validating', label: 'Validating', description: 'Pre-sync validation in progress' },
      { value: 'validation_failed', label: 'Validation Failed', description: 'Failed validation - needs fixes' },
      { value: 'needs_review', label: 'Needs Review', description: 'Has warnings but can proceed' },
    ],
  },
  {
    label: 'Terminal',
    states: [
      { value: 'failed', label: 'Failed', description: 'Processing failed - can retry' },
      { value: 'quarantined', label: 'Quarantined', description: 'Max retries - needs manual intervention' },
      { value: 'skipped', label: 'Skipped', description: 'Manually excluded' },
    ],
  },
] as const

// Flat list for backward compatibility
const states: FestivalState[] = stateGroups.flatMap(g => g.states.map(s => s.value as FestivalState))

type SortField = 'created_at' | 'name' | 'state' | 'source' | 'retry_count' | 'validation_status'
type SortDirection = 'asc' | 'desc'

export default function FestivalsPage() {
  const queryClient = useQueryClient()
  const { success, error: toastError } = useToast()

  // Filters
  const [search, setSearch] = useState('')
  const [state, setState] = useState('')
  const [source, setSource] = useState('')
  const [offset, setOffset] = useState(0)

  // Sorting
  const [sortField, setSortField] = useState<SortField>('created_at')
  const [sortDirection, setSortDirection] = useState<SortDirection>('desc')

  // Selection
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set())

  // Bulk research result
  const [bulkResult, setBulkResult] = useState<any>(null)

  // Dialogs
  const [skipDialogOpen, setSkipDialogOpen] = useState(false)
  const [resetDialogOpen, setResetDialogOpen] = useState(false)
  const [bulkActionLoading, setBulkActionLoading] = useState(false)

  // Edit dialog state
  const [editingFestival, setEditingFestival] = useState<any>(null)

  const limit = 20

  const { data, isLoading, refetch } = useQuery({
    queryKey: ['festivals', { search, state, source, offset, limit }],
    queryFn: () =>
      getFestivals({
        search: search || undefined,
        state: state || undefined,
        source: source || undefined,
        offset,
        limit,
      }),
  })

  // Extract unique sources from data for the filter dropdown
  const availableSources = useMemo(() => {
    const sources = new Set<string>()
    data?.festivals?.forEach((f: any) => {
      if (f.source) sources.add(f.source)
    })
    return Array.from(sources).sort()
  }, [data?.festivals])

  // Client-side sorting
  const sortedFestivals = useMemo(() => {
    if (!data?.festivals) return []
    const items = [...data.festivals]
    const dir = sortDirection === 'asc' ? 1 : -1
    items.sort((a: any, b: any) => {
      switch (sortField) {
        case 'name':
          return (a.name || '').localeCompare(b.name || '') * dir
        case 'state':
          return (a.state || '').localeCompare(b.state || '') * dir
        case 'source':
          return (a.source || '').localeCompare(b.source || '') * dir
        case 'retry_count':
          return ((a.retry_count || 0) - (b.retry_count || 0)) * dir
        case 'validation_status': {
          const order = ['ready', 'needs_review', 'invalid', 'pending']
          const aIdx = order.indexOf(a.validation_status || 'pending')
          const bIdx = order.indexOf(b.validation_status || 'pending')
          return (aIdx - bIdx) * dir
        }
        case 'created_at':
        default:
          return (
            (new Date(a.created_at || 0).getTime() -
              new Date(b.created_at || 0).getTime()) *
            dir
          )
      }
    })
    return items
  }, [data?.festivals, sortField, sortDirection])

  const allSelectedOnPage =
    sortedFestivals.length > 0 &&
    sortedFestivals.every((f: any) => selectedIds.has(f.id))

  const toggleSelectAll = () => {
    if (allSelectedOnPage) {
      // Deselect only the ones on this page
      const pageIds = new Set(sortedFestivals.map((f: any) => f.id))
      setSelectedIds((prev) => {
        const next = new Set(prev)
        pageIds.forEach((id) => next.delete(id))
        return next
      })
    } else {
      // Select all on this page
      setSelectedIds((prev) => {
        const next = new Set(prev)
        sortedFestivals.forEach((f: any) => next.add(f.id))
        return next
      })
    }
  }

  const toggleSelect = (id: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  const clearSelection = () => setSelectedIds(new Set())

  const selectedFestivals = useMemo(
    () => sortedFestivals.filter((f: any) => selectedIds.has(f.id)),
    [sortedFestivals, selectedIds]
  )

  const hasSelected = selectedIds.size > 0

  // State-based action eligibility
  const canDeduplicate = selectedFestivals.some((f: any) => f.state === 'discovered')
  const canResearch = selectedFestivals.some(
    (f: any) =>
      f.state === 'researching' ||
      f.state === 'researched' ||
      f.state === 'researched_partial' ||
      f.state === 'failed'
  )
  const canSync = selectedFestivals.some((f: any) => f.state === 'researched')
  const canRetry = selectedFestivals.some((f: any) => f.state === 'failed')
  const canSkip = selectedFestivals.length > 0
  const canReset = selectedFestivals.length > 0

  // Mutations
  const bulkResearchMutation = useMutation({
    mutationFn: bulkResearchFestivals,
    onSuccess: (result) => {
      setBulkResult(result)
      queryClient.invalidateQueries({ queryKey: ['festivals'] })
      queryClient.invalidateQueries({ queryKey: ['stats'] })
      setTimeout(() => setBulkResult(null), 5000)
    },
  })

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault()
    setOffset(0)
    clearSelection()
    refetch()
  }

  const toggleSort = (field: SortField) => {
    if (sortField === field) {
      setSortDirection(sortDirection === 'asc' ? 'desc' : 'asc')
    } else {
      setSortField(field)
      setSortDirection('desc')
    }
  }

  const runBulkAction = async (
    action: 'deduplicate' | 'research' | 'sync' | 'retry' | 'skip' | 'reset',
    reason?: string
  ) => {
    const ids = selectedFestivals.map((f: any) => f.id)
    if (ids.length === 0) return
    setBulkActionLoading(true)

    const results = await Promise.allSettled(
      ids.map((id: string) => {
        switch (action) {
          case 'deduplicate':
            return deduplicateFestival(id)
          case 'research':
            return researchFestival(id)
          case 'sync':
            return syncFestival(id)
          case 'retry':
            return retryFestival(id)
          case 'skip':
            return skipFestival(id, reason || 'Bulk skip')
          case 'reset':
            return resetFestival(id, 'discovered')
        }
      })
    )

    const succeeded = results.filter((r) => r.status === 'fulfilled').length
    const failed = results.filter((r) => r.status === 'rejected').length

    queryClient.invalidateQueries({ queryKey: ['festivals'] })
    queryClient.invalidateQueries({ queryKey: ['stats'] })
    clearSelection()
    setBulkActionLoading(false)

    if (failed === 0) {
      success(`${action} succeeded for ${succeeded} festivals`)
    } else {
      toastError(`${action}: ${succeeded} succeeded, ${failed} failed`)
    }
  }

  const SortButton = ({
    field,
    label,
  }: {
    field: SortField
    label: string
  }) => (
    <button
      onClick={() => toggleSort(field)}
      className={`flex items-center gap-1 hover:text-foreground transition-colors ${
        sortField === field ? 'text-foreground font-medium' : ''
      }`}
    >
      {label}
      {sortField === field && (
        <ArrowUpDown
          className={`h-3 w-3 ${sortDirection === 'asc' ? 'rotate-180' : ''}`}
        />
      )}
    </button>
  )

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
        <h1 className="text-2xl sm:text-3xl font-bold">Festivals</h1>
        <div className="flex gap-2">
          <Button
            onClick={() =>
              bulkResearchMutation.mutate({
                failure_reason: 'dates',
                limit: 50,
              })
            }
            disabled={bulkResearchMutation.isPending}
            variant="outline"
            size="sm"
          >
            <PlayCircle className="h-4 w-4 mr-2" />
            Bulk Research Failed
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
                  Daily used: {bulkResult.daily_used}/50 | Remaining:{bulkResult.daily_remaining}
                </p>
              </div>
              <Button variant="ghost" size="sm" onClick={() => setBulkResult(null)}>
                Dismiss
              </Button>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Bulk Action Toolbar */}
      {hasSelected && (
        <Card className="border-primary">
          <CardContent className="py-3">
            <div className="flex flex-col sm:flex-row sm:items-center gap-3">
              <div className="flex items-center gap-2 text-sm font-medium">
                <CheckSquare className="h-4 w-4 text-primary" />
                {selectedIds.size} selected
              </div>
              <div className="flex flex-wrap gap-2">
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => runBulkAction('deduplicate')}
                  disabled={!canDeduplicate || bulkActionLoading}
                >
                  <SearchIcon className="h-3.5 w-3.5 mr-1" />
                  Deduplicate
                </Button>
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => runBulkAction('research')}
                  disabled={!canResearch || bulkActionLoading}
                >
                  <RotateCcw className="h-3.5 w-3.5 mr-1" />
                  Research
                </Button>
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => runBulkAction('sync')}
                  disabled={!canSync || bulkActionLoading}
                >
                  <Upload className="h-3.5 w-3.5 mr-1" />
                  Sync
                </Button>
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => runBulkAction('retry')}
                  disabled={!canRetry || bulkActionLoading}
                >
                  <RefreshCw className="h-3.5 w-3.5 mr-1" />
                  Retry
                </Button>
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => setSkipDialogOpen(true)}
                  disabled={!canSkip || bulkActionLoading}
                >
                  <SkipForward className="h-3.5 w-3.5 mr-1" />
                  Skip
                </Button>
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => setResetDialogOpen(true)}
                  disabled={!canReset || bulkActionLoading}
                >
                  <AlertTriangle className="h-3.5 w-3.5 mr-1" />
                  Reset
                </Button>
              </div>
              <div className="flex-1" />
              <Button
                size="sm"
                variant="ghost"
                onClick={clearSelection}
                disabled={bulkActionLoading}
              >
                <X className="h-3.5 w-3.5 mr-1" />
                Clear
              </Button>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Filters */}
      <Card>
        <CardContent className="pt-6">
          <form onSubmit={handleSearch} className="flex flex-col gap-3">
            <div className="flex flex-col sm:flex-row gap-3">
              <div className="flex-1">
                <Input
                  placeholder="Search festivals..."
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  className="w-full"
                />
              </div>
              <div className="flex gap-3">
                <Select
                  value={state}
                  onChange={(e) => {
                    setState(e.target.value)
                    setOffset(0)
                    clearSelection()
                  }}
                  className="w-full sm:w-64"
                  title={stateGroups.find(g => g.states.find(s => s.value === state))?.states.find(s => s.value === state)?.description || 'Filter by state'}
                >
                  <option value="">All States</option>
                  {stateGroups.map((group) => (
                    <optgroup key={group.label} label={group.label}>
                      {group.states.map((s) => (
                        <option key={s.value} value={s.value} title={s.description}>
                          {s.label}
                        </option>
                      ))}
                    </optgroup>
                  ))}
                </Select>
                <Select
                  value={source}
                  onChange={(e) => {
                    setSource(e.target.value)
                    setOffset(0)
                    clearSelection()
                  }}
                  className="w-full sm:w-44"
                >
                  <option value="">All Sources</option>
                  {availableSources.map((s) => (
                    <option key={s} value={s}>
                      {s}
                    </option>
                  ))}
                </Select>
                <Button type="submit" className="shrink-0">
                  <Search className="h-4 w-4 mr-2" />
                  Search
                </Button>
              </div>
            </div>

            {/* Sort bar */}
            <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-sm text-muted-foreground border-t pt-3 mt-1">
              <span className="text-xs uppercase tracking-wider">Sort by:</span>
              <SortButton field="created_at" label="Date" />
              <SortButton field="name" label="Name" />
              <SortButton field="state" label="State" />
              <SortButton field="source" label="Source" />
              <SortButton field="retry_count" label="Retries" />
            </div>
          </form>
        </CardContent>
      </Card>

      {/* Results */}
      <Card>
        <CardHeader className="flex flex-row items-center justify-between">
          <CardTitle>{data ? `${data.total} Festivals` : 'Loading...'}</CardTitle>
          {sortedFestivals.length > 0 && (
            <button
              onClick={toggleSelectAll}
              className="flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground transition-colors"
            >
              {allSelectedOnPage ? (
                <CheckSquare className="h-4 w-4" />
              ) : (
                <Square className="h-4 w-4" />
              )}
              {allSelectedOnPage ? 'Deselect all' : 'Select all'}
            </button>
          )}
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <SkeletonList rows={5} />
          ) : sortedFestivals?.length === 0 ? (
            <EmptyState
              icon={Music}
              title="No festivals found"
              description="Try adjusting your search or filters, or run discovery to find new festivals."
            />
          ) : (
            <div className="space-y-2">
              {/* Header row with sort buttons — hidden on mobile */}
              <div className="hidden sm:flex items-center justify-between px-4 py-2 text-sm text-muted-foreground border-b">
                <div className="flex items-center gap-3 flex-1">
                  <div className="w-5" />
                  <span>Festival</span>
                </div>
                <div className="flex items-center gap-4">
                  <SortButton field="validation_status" label="Validation" />
                  <SortButton field="retry_count" label="Retries" />
                  <span>State</span>
                </div>
              </div>

              {sortedFestivals?.map((festival: any) => {
                const tags = extractTagsFromResearchData(festival.research_data)
                const isSelected = selectedIds.has(festival.id)
                return (
                  <div
                    key={festival.id}
                    className={`flex flex-col sm:flex-row sm:items-center sm:justify-between rounded-lg border p-3 sm:p-4 transition-colors gap-2 sm:gap-0 ${
                      isSelected ? 'bg-primary/5 border-primary/30' : 'hover:bg-muted'
                    }`}
                  >
                    <div className="flex items-start sm:items-center gap-3 sm:gap-4 min-w-0">
                      <Checkbox
                        checked={isSelected}
                        onCheckedChange={() => toggleSelect(festival.id)}
                        className="mt-0.5 sm:mt-0 shrink-0"
                        onClick={(e) => e.stopPropagation()}
                      />
                      {/* State Indicator Dot with Tooltip */}
                      <div className="group relative shrink-0 mt-1.5 sm:mt-0">
                        <div
                          className={`w-3 h-3 rounded-full ${getStateColor(festival.state)} cursor-help`}
                        />
                        {/* Tooltip */}
                        <div className="absolute left-full top-1/2 -translate-y-1/2 ml-2 hidden group-hover:block w-56 p-2.5 rounded-lg border bg-card shadow-lg z-20">
                          <p className="text-xs font-medium mb-1">{getStateLabel(festival.state)}</p>
                          <p className="text-xs text-muted-foreground leading-relaxed">
                            {getStateDescription(festival.state)}
                          </p>
                        </div>
                      </div>
                      <div className="min-w-0">
                        <Link
                          href={`/festivals/${festival.id}`}
                          className="font-medium text-sm sm:text-base hover:text-primary"
                        >
                          {festival.name}
                        </Link>
                        <p className="text-xs sm:text-sm text-muted-foreground">
                          Source: {festival.source} •{' '}
                          {formatRelativeTime(festival.created_at)}
                        </p>
                        <TagList tags={tags} className="mt-1.5" max={3} />
                      </div>
                    </div>
                    <div className="flex items-center gap-2 sm:gap-3 shrink-0 ml-8 sm:ml-0">
                      {/* Workflow Type Badge */}
                      {festival.workflow_type && (
                        <Badge
                          variant={festival.workflow_type === 'new' ? 'default' : 'secondary'}
                          className={festival.workflow_type === 'new' ? 'bg-blue-500 text-xs' : 'text-xs'}
                        >
                          {festival.workflow_type === 'new' ? (
                            <><Plus className="h-3 w-3 mr-1" /> New</>
                          ) : (
                            <><RotateCcw className="h-3 w-3 mr-1" /> Update</>
                          )}
                        </Badge>
                      )}

                      {/* Update Reasons Tooltip */}
                      {festival.update_reasons && festival.update_reasons.length > 0 && (
                        <div className="group relative">
                          <Badge variant="outline" className="text-xs cursor-help">
                            <Info className="h-3 w-3 mr-1" />
                            {festival.update_reasons.length} reason{festival.update_reasons.length > 1 ? 's' : ''}
                          </Badge>
                          <div className="absolute bottom-full right-0 mb-2 hidden group-hover:block w-48 p-2 rounded-lg border bg-card shadow-lg z-10">
                            <p className="text-xs font-medium mb-1">Update reasons:</p>
                            <ul className="text-xs text-muted-foreground space-y-0.5">
                              {festival.update_reasons.map((reason: string, idx: number) => (
                                <li key={idx}>• {reason.replace(/_/g, ' ')}</li>
                              ))}
                            </ul>
                          </div>
                        </div>
                      )}

                      {/* Sync Result */}
                      {festival.sync_data && festival.sync_data.action && (
                        <Badge
                          variant="outline"
                          className={`text-xs capitalize ${
                            festival.sync_data.action === 'created'
                              ? 'border-green-500 text-green-600 bg-green-50 dark:bg-green-950/20'
                              : festival.sync_data.action === 'updated'
                                ? 'border-blue-500 text-blue-600 bg-blue-50 dark:bg-blue-950/20'
                                : festival.sync_data.action === 'added_event_date'
                                  ? 'border-purple-500 text-purple-600 bg-purple-50 dark:bg-purple-950/20'
                                  : 'border-gray-500 text-gray-600 bg-gray-50 dark:bg-gray-950/20'
                          }`}
                        >
                          {festival.sync_data.action === 'added_event_date'
                            ? 'New Date'
                            : festival.sync_data.action}
                        </Badge>
                      )}

                      {/* Quick Edit Button for editable states */}
                      {(festival.state === 'researched_partial' ||
                        festival.state === 'researched' ||
                        festival.state === 'validation_failed' ||
                        festival.state === 'needs_review') && (
                        <button
                          onClick={(e) => {
                            e.stopPropagation()
                            setEditingFestival(festival)
                          }}
                          className="inline-flex items-center gap-1 rounded-full bg-blue-100 px-2 py-0.5 text-xs font-medium text-blue-700 hover:bg-blue-200 dark:bg-blue-900 dark:text-blue-200"
                          title="Edit festival details"
                        >
                          <Edit className="h-3 w-3" />
                          Edit
                        </button>
                      )}
                      {festival.partymap_event_id && (
                        <a
                          href={
                            getPartyMapUrl(
                              festival.partymap_event_id,
                              festival.partymap_date_id
                            ) || undefined
                          }
                          target="_blank"
                          rel="noopener noreferrer"
                          className="inline-flex items-center gap-1 rounded-full bg-green-100 px-2 py-0.5 text-xs font-medium text-green-700 hover:bg-green-200 dark:bg-green-900 dark:text-green-200"
                          onClick={(e) => e.stopPropagation()}
                        >
                          <ExternalLink className="h-3 w-3" />
                          PartyMap
                        </a>
                      )}
                      {festival.validation_status &&
                        festival.validation_status !== 'pending' && (
                          <ValidationBadge
                            status={festival.validation_status}
                            showLabel={false}
                          />
                        )}
                      {festival.retry_count > 0 && (
                        <RetryCountBadge count={festival.retry_count} />
                      )}
                      {/* State Badge with Tooltip */}
                      <div className="group relative">
                        <Badge
                          variant="secondary"
                          className={`${getStateColor(festival.state)} text-white text-xs sm:text-sm cursor-help`}
                        >
                          {getStateLabel(festival.state)}
                        </Badge>
                        {/* Tooltip */}
                        <div className="absolute bottom-full right-0 mb-2 hidden group-hover:block w-56 p-2.5 rounded-lg border bg-card shadow-lg z-20">
                          <p className="text-xs font-medium mb-1">{getStateLabel(festival.state)}</p>
                          <p className="text-xs text-muted-foreground leading-relaxed">
                            {getStateDescription(festival.state)}
                          </p>
                        </div>
                      </div>
                    </div>
                  </div>
                )
              })}
            </div>
          )}

          {/* Pagination */}
          {data && data.total > limit && (
            <div className="flex items-center justify-between mt-6">
              <Button
                variant="outline"
                disabled={offset === 0}
                onClick={() => {
                  setOffset(Math.max(0, offset - limit))
                  clearSelection()
                }}
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
                onClick={() => {
                  setOffset(offset + limit)
                  clearSelection()
                }}
              >
                Next
              </Button>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Skip dialog */}
      <PromptDialog
        open={skipDialogOpen}
        title="Skip Festivals"
        description={`Provide a reason for skipping ${selectedIds.size} selected festival(s).`}
        placeholder="Reason for skipping..."
        confirmLabel="Skip"
        onConfirm={(reason) => {
          runBulkAction('skip', reason)
          setSkipDialogOpen(false)
        }}
        onCancel={() => setSkipDialogOpen(false)}
      />

      {/* Reset dialog */}
      <ConfirmDialog
        open={resetDialogOpen}
        title="Reset Festivals"
        description={`Reset ${selectedIds.size} selected festival(s) to discovered state? This will clear research and sync data.`}
        confirmLabel="Reset"
        variant="destructive"
        onConfirm={() => {
          runBulkAction('reset')
          setResetDialogOpen(false)
        }}
        onCancel={() => setResetDialogOpen(false)}
      />

      {/* Festival Editor Dialog */}
      {editingFestival && (
        <FestivalEditor
          festivalId={editingFestival.id}
          festivalName={editingFestival.name}
          initialData={editingFestival.research_data}
          currentState={editingFestival.state}
          open={!!editingFestival}
          onOpenChange={(open) => {
            if (!open) setEditingFestival(null)
          }}
        />
      )}
    </div>
  )
}
