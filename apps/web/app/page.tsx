'use client'

import { useQuery } from '@tanstack/react-query'
import {
  getStats,
  getPendingFestivals,
  getJobsStatus,
  getErrorStats,
  getRefreshStats,
  getHealth,
  getSchedulingStatus,
  getAutoProcessStatus,
  getJobActivity,
  getThreads,
  runDiscovery,
} from '@/lib/api'
import { useJobWebSocket } from '@/lib/hooks/use-job-websocket'
import { useThreadWebSocket } from '@/lib/hooks/use-thread-websocket'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Alert, AlertTitle, AlertDescription, AlertAction } from '@/components/ui/alert'
import { Separator } from '@/components/ui/separator'
import {
  formatCurrency,
  getStateColor,
  getStateLabel,
  formatRelativeTime,
  cn,
} from '@/lib/utils'
import {
  Music,
  DollarSign,
  AlertCircle,
  CheckCircle,
  Clock,
  RefreshCw,
  Activity,
  ShieldAlert,
  ShieldCheck,
  Wifi,
  WifiOff,
  CalendarCheck,
  Zap,
  AlertTriangle,
  TrendingUp,
  Loader2,
  Bot,
  Search,
  Brain,
  X,
  Radio,
  ExternalLink,
  BarChart3,
} from 'lucide-react'
import Link from 'next/link'
import { useState, useMemo } from 'react'
import { useToast } from '@/components/ui/toast-provider'
import { StateBadge } from '@/components/state-badge'
import { ThreadStreamModal } from '@/components/ThreadStreamModal'
import type { JobStatusDetail } from '@/types'
import type { Thread } from '@/lib/api'

export default function DashboardPage() {
  const [isRunningDiscovery, setIsRunningDiscovery] = useState(false)
  const [selectedThreadId, setSelectedThreadId] = useState<string | null>(null)
  const [activityOffset, setActivityOffset] = useState(0)
  const activityLimit = 10
  const { success } = useToast()

  const { statuses: wsStatuses, isConnected: wsConnected } = useJobWebSocket()
  const { liveThreads, isConnected: threadWsConnected, lastUpdate } = useThreadWebSocket()

  const { data: stats, refetch: refetchStats } = useQuery({
    queryKey: ['stats'],
    queryFn: getStats,
    refetchInterval: 30000,
  })

  const { data: pending } = useQuery({
    queryKey: ['pending', 5],
    queryFn: () => getPendingFestivals(undefined, 5),
    refetchInterval: 30000,
  })

  const { data: jobsRest } = useQuery({
    queryKey: ['jobs'],
    queryFn: getJobsStatus,
    refetchInterval: 30000,
  })

  const { data: errorStats } = useQuery({
    queryKey: ['error-stats'],
    queryFn: getErrorStats,
    refetchInterval: 30000,
  })

  const { data: refreshStats } = useQuery({
    queryKey: ['refresh-stats'],
    queryFn: getRefreshStats,
    refetchInterval: 30000,
  })

  const { data: health } = useQuery({
    queryKey: ['health'],
    queryFn: getHealth,
    refetchInterval: 30000,
  })

  const { data: scheduling } = useQuery({
    queryKey: ['scheduling'],
    queryFn: getSchedulingStatus,
    refetchInterval: 30000,
  })

  const { data: autoProcess } = useQuery({
    queryKey: ['auto-process'],
    queryFn: getAutoProcessStatus,
    refetchInterval: 30000,
  })

  const { data: jobActivity } = useQuery({
    queryKey: ['job-activity', activityLimit, activityOffset],
    queryFn: () => getJobActivity(undefined, activityLimit, activityOffset),
    refetchInterval: 10000,
  })

  // Fetch threads for all agent types
  const { data: researchThreads } = useQuery({
    queryKey: ['threads', 'research'],
    queryFn: () => getThreads('research', 20),
    refetchInterval: 5000,
  })

  const { data: discoveryThreads } = useQuery({
    queryKey: ['threads', 'discovery'],
    queryFn: () => getThreads('discovery', 20),
    refetchInterval: 5000,
  })

  const { data: goabaseThreads } = useQuery({
    queryKey: ['threads', 'goabase'],
    queryFn: () => getThreads('goabase', 20),
    refetchInterval: 5000,
  })

  // Merge WebSocket job statuses with REST fallback
  const jobs = wsStatuses || jobsRest

  // Process and combine threads with performance optimization
  const allThreads = useMemo(() => {
    const restThreads = [
      ...(researchThreads?.threads || []),
      ...(discoveryThreads?.threads || []),
      ...(goabaseThreads?.threads || []),
    ]

    // Merge with WebSocket live updates
    const threadMap = new Map<string, Thread>()
    
    // Add REST threads first
    restThreads.forEach((t) => threadMap.set(t.thread_id, t))
    
    // Override with live WebSocket updates
    liveThreads.forEach((t) => threadMap.set(t.thread_id, { ...threadMap.get(t.thread_id), ...t } as Thread))
    
    return Array.from(threadMap.values()).sort(
      (a, b) => new Date(b.started_at).getTime() - new Date(a.started_at).getTime()
    )
  }, [researchThreads, discoveryThreads, goabaseThreads, liveThreads, lastUpdate])

  const runningThreads = useMemo(() => allThreads.filter((t) => t.status === 'running'), [allThreads])
  const completedThreads = useMemo(() => allThreads.filter((t) => t.status === 'completed').slice(0, 10), [allThreads])
  const failedThreads = useMemo(() => allThreads.filter((t) => t.status === 'failed').slice(0, 5), [allThreads])
  const hasAnyThreads = runningThreads.length > 0 || completedThreads.length > 0 || failedThreads.length > 0

  const getAgentIcon = (agentType: string) => {
    switch (agentType) {
      case 'research': return <Brain className="h-4 w-4" />
      case 'discovery': return <Search className="h-4 w-4" />
      case 'goabase': return <Bot className="h-4 w-4" />
      default: return <Activity className="h-4 w-4" />
    }
  }

  const getThreadName = (thread: Thread) => {
    if (thread.event_name) return thread.event_name
    if (thread.result_data?.name) return thread.result_data.name as string
    if (thread.result_data?.festival_name) return thread.result_data.festival_name as string
    return `${thread.agent_type} - ${thread.thread_id.slice(-8)}`
  }

  const getThreadDuration = (thread: Thread) => {
    const start = new Date(thread.started_at)
    const end = thread.completed_at ? new Date(thread.completed_at) : new Date()
    const diff = end.getTime() - start.getTime()
    const minutes = Math.floor(diff / 60000)
    const seconds = Math.floor((diff % 60000) / 1000)
    if (minutes > 0) return `${minutes}m ${seconds}s`
    return `${seconds}s`
  }

  const handleRunDiscovery = async () => {
    setIsRunningDiscovery(true)
    try {
      await runDiscovery()
      refetchStats()
      success('Discovery started successfully')
    } catch {
      // Error toast handled by API interceptor
    } finally {
      setIsRunningDiscovery(false)
    }
  }

  const stateOrder = [
    'discovered',
    'researching',
    'researched',
    'syncing',
    'synced',
    'failed',
    'skipped',
  ]

  const isHealthy = health?.status === 'ok'
  const schedulingEnabled = scheduling?.scheduling_enabled
  const autoProcessEnabled = autoProcess?.enabled
  const pendingRefreshCount = refreshStats?.pending ?? 0

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h1 className="text-2xl sm:text-3xl font-bold">Dashboard</h1>
        <div className="flex items-center gap-3">
          {/* System Status Indicators */}
          <div className="hidden md:flex items-center gap-2 text-xs text-muted-foreground">
            {wsConnected ? (
              <Wifi className="h-3.5 w-3.5 text-green-500" />
            ) : (
              <WifiOff className="h-3.5 w-3.5 text-muted-foreground" />
            )}
            <span className={wsConnected ? 'text-green-500' : ''}>
              {wsConnected ? 'Live' : 'Polling'}
            </span>
            {isHealthy ? (
              <ShieldCheck className="h-3.5 w-3.5 text-green-500 ml-2" />
            ) : (
              <ShieldAlert className="h-3.5 w-3.5 text-yellow-500 ml-2" />
            )}
            <span>{isHealthy ? 'Healthy' : 'Degraded'}</span>
            {schedulingEnabled ? (
              <CalendarCheck className="h-3.5 w-3.5 text-green-500 ml-2" />
            ) : (
              <Clock className="h-3.5 w-3.5 text-muted-foreground ml-2" />
            )}
            <span>{schedulingEnabled ? 'Scheduled' : 'Manual'}</span>
            {autoProcessEnabled && (
              <Zap className="h-3.5 w-3.5 text-green-500 ml-2" />
            )}
            {autoProcessEnabled && <span>Auto</span>}
          </div>
          <Button
            onClick={handleRunDiscovery}
            disabled={isRunningDiscovery}
            className="gap-2"
          >
            <RefreshCw
              className={cn('h-4 w-4', isRunningDiscovery && 'animate-spin')}
            />
            Run Discovery
          </Button>
        </div>
      </div>

      {/* Refresh Approvals Alert */}
      {pendingRefreshCount > 0 && (
        <Alert variant="destructive" className="border-orange-500/50 bg-orange-50 text-orange-900 dark:bg-orange-950/20 dark:text-orange-100">
          <AlertTriangle className="h-4 w-4 text-orange-600 dark:text-orange-400" />
          <AlertTitle>Refresh Pipeline</AlertTitle>
          <AlertDescription>
            {pendingRefreshCount} approval{pendingRefreshCount > 1 ? 's' : ''} pending review
          </AlertDescription>
          <AlertAction>
            <Link href="/refresh">
              <Button size="sm" variant="outline">
                Review
              </Button>
            </Link>
          </AlertAction>
        </Alert>
      )}

      {/* Stats Grid */}
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Total Festivals</CardTitle>
            <Music className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{stats?.total_festivals ?? 0}</div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Today's Cost</CardTitle>
            <DollarSign className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              {formatCurrency(stats?.today_cost_cents ?? 0)}
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Week's Cost</CardTitle>
            <TrendingUp className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              {formatCurrency(stats?.week_cost_cents ?? 0)}
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Month's Cost</CardTitle>
            <DollarSign className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              {formatCurrency(stats?.month_cost_cents ?? 0)}
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Pending Actions</CardTitle>
            <Clock className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{stats?.pending_count ?? 0}</div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Failed</CardTitle>
            <AlertCircle className="h-4 w-4 text-destructive" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-destructive">
              {stats?.failed_count ?? 0}
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Festival States */}
      <Card>
        <CardHeader>
          <CardTitle>Festival States</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex flex-wrap gap-2">
            {stats?.by_state &&
              stateOrder.map((state) => {
                const count =
                  stats.by_state[state as keyof typeof stats.by_state] ?? 0
                if (count === 0) return null
                return (
                  <StateBadge key={state} state={state}>
                    {count}
                  </StateBadge>
                )
              })}
          </div>
        </CardContent>
      </Card>

      {/* Active Threads Summary */}
      <Card>
        <CardHeader className="flex flex-row items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-lg bg-primary/10">
              <Radio className="h-5 w-5 text-primary" />
            </div>
            <div>
              <CardTitle>Agent Threads</CardTitle>
              <p className="text-sm text-muted-foreground">
                Active and recently completed agent runs
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            {threadWsConnected && (
              <Badge variant="outline" className="text-xs border-green-500 text-green-600 bg-green-50 dark:bg-green-950/20">
                <Wifi className="h-3 w-3 mr-1" />
                Live
              </Badge>
            )}
            <Link href="/jobs">
              <Button variant="ghost" size="sm">
                View All
              </Button>
            </Link>
          </div>
        </CardHeader>
        <CardContent>
          {hasAnyThreads ? (
            <div className="space-y-6">
              {/* Running Threads */}
              {runningThreads.length > 0 && (
                <div className="space-y-2">
                  <div className="flex items-center gap-2">
                    <div className="w-2 h-2 rounded-full bg-green-500 animate-pulse" />
                    <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">
                      Running ({runningThreads.length})
                    </p>
                  </div>
                  <div className="grid gap-2">
                    {runningThreads.map((thread) => (
                      <button
                        key={thread.thread_id}
                        onClick={() => setSelectedThreadId(thread.thread_id)}
                        className="flex items-center justify-between rounded-lg border p-3 text-left hover:border-primary/50 hover:bg-muted/50 transition-colors group"
                      >
                        <div className="flex items-center gap-3 min-w-0">
                          <div className="p-2 rounded-md bg-green-500/10 text-green-500 flex-shrink-0">
                            {getAgentIcon(thread.agent_type)}
                          </div>
                          <div className="min-w-0">
                            <p className="font-medium truncate">{getThreadName(thread)}</p>
                            <div className="flex items-center gap-3 text-xs text-muted-foreground mt-0.5">
                              <span className="capitalize">{thread.agent_type}</span>
                              <span>•</span>
                              <span>Started {formatRelativeTime(thread.started_at)}</span>
                              <span>•</span>
                              <span>{getThreadDuration(thread)}</span>
                            </div>
                          </div>
                        </div>
                        <div className="flex items-center gap-3 flex-shrink-0">
                          {thread.cost_cents > 0 && (
                            <span className="text-xs text-muted-foreground">
                              {formatCurrency(thread.cost_cents)}
                            </span>
                          )}
                          {thread.total_tokens > 0 && (
                            <span className="text-xs text-muted-foreground">
                              {thread.total_tokens.toLocaleString()} tokens
                            </span>
                          )}
                          <Loader2 className="h-4 w-4 animate-spin text-green-500" />
                        </div>
                      </button>
                    ))}
                  </div>
                </div>
              )}

              {/* Completed + Failed in columns */}
              <div className="grid gap-6 md:grid-cols-2">
                {/* Recent Completed */}
                {completedThreads.length > 0 && (
                  <div className="space-y-2">
                    <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">
                      Recently Completed ({completedThreads.length})
                    </p>
                    <div className="space-y-2">
                      {completedThreads.map((thread) => (
                        <button
                          key={thread.thread_id}
                          onClick={() => setSelectedThreadId(thread.thread_id)}
                          className="w-full flex items-center justify-between rounded-lg border p-3 text-left hover:border-primary/50 hover:bg-muted/50 transition-colors"
                        >
                          <div className="flex items-center gap-3 min-w-0">
                            <div className="p-1.5 rounded-md bg-muted flex-shrink-0">
                              {getAgentIcon(thread.agent_type)}
                            </div>
                            <div className="min-w-0">
                              <p className="font-medium text-sm truncate">{getThreadName(thread)}</p>
                              <p className="text-xs text-muted-foreground capitalize">
                                {thread.agent_type} • {formatRelativeTime(thread.started_at)}
                              </p>
                            </div>
                          </div>
                          <div className="flex items-center gap-2 flex-shrink-0">
                            {thread.cost_cents > 0 && (
                              <span className="text-xs text-muted-foreground">
                                {formatCurrency(thread.cost_cents)}
                              </span>
                            )}
                            <CheckCircle className="h-4 w-4 text-muted-foreground" />
                          </div>
                        </button>
                      ))}
                    </div>
                  </div>
                )}

                {/* Recent Failed */}
                {failedThreads.length > 0 && (
                  <div className="space-y-2">
                    <p className="text-xs font-semibold text-destructive uppercase tracking-wide">
                      Failed ({failedThreads.length})
                    </p>
                    <div className="space-y-2">
                      {failedThreads.map((thread) => (
                        <button
                          key={thread.thread_id}
                          onClick={() => setSelectedThreadId(thread.thread_id)}
                          className="w-full flex items-center justify-between rounded-lg border border-destructive/30 p-3 text-left hover:border-destructive/50 hover:bg-destructive/5 transition-colors"
                        >
                          <div className="flex items-center gap-3 min-w-0">
                            <div className="p-1.5 rounded-md bg-destructive/10 text-destructive flex-shrink-0">
                              {getAgentIcon(thread.agent_type)}
                            </div>
                            <div className="min-w-0">
                              <p className="font-medium text-sm truncate">{getThreadName(thread)}</p>
                              <p className="text-xs text-muted-foreground capitalize">
                                {thread.agent_type} • {formatRelativeTime(thread.started_at)}
                              </p>
                            </div>
                          </div>
                          <X className="h-4 w-4 text-destructive flex-shrink-0" />
                        </button>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            </div>
          ) : (
            <div className="text-center py-12">
              <Bot className="h-12 w-12 mx-auto mb-4 text-muted-foreground opacity-30" />
              <p className="text-muted-foreground font-medium">No agent threads yet</p>
              <p className="text-sm text-muted-foreground mt-1">
                Run discovery or start a research job to see threads here
              </p>
              <Button
                onClick={handleRunDiscovery}
                disabled={isRunningDiscovery}
                className="gap-2 mt-4"
                size="sm"
              >
                <RefreshCw className={cn('h-4 w-4', isRunningDiscovery && 'animate-spin')} />
                Run Discovery
              </Button>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Two-column layout for Active Jobs + Error/DLQ */}
      <div className="grid gap-6 lg:grid-cols-2">
        {/* Active Jobs */}
        <Card>
          <CardHeader className="flex flex-row items-center justify-between">
            <CardTitle>Active Jobs</CardTitle>
            <Link href="/jobs">
              <Button variant="ghost" size="sm">
                Manage Jobs
              </Button>
            </Link>
          </CardHeader>
          <CardContent className="space-y-4">
            {['discovery', 'research', 'sync', 'goabase'].map((jobType) => {
              const job = jobs?.[jobType]
              const isRunning = job?.status === 'running'
              const progress = job?.progress
              const processing = job?.currently_processing

              return (
                <div
                  key={jobType}
                  className="rounded-lg border p-3 space-y-2"
                >
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      {isRunning ? (
                        <Activity className="h-4 w-4 text-green-500 animate-pulse" />
                      ) : (
                        <CheckCircle className="h-4 w-4 text-muted-foreground" />
                      )}
                      <span className="capitalize font-medium">{jobType}</span>
                    </div>
                    <Badge variant={isRunning ? 'default' : 'secondary'}>
                      {isRunning ? 'Running' : 'Idle'}
                    </Badge>
                  </div>

                  {/* Progress Bar */}
                  {isRunning && progress && (
                    <div className="space-y-1">
                      <div className="flex justify-between text-xs text-muted-foreground">
                        <span>Progress</span>
                        <span>
                          {progress.current} / {progress.total} (
                          {progress.percent}%)
                        </span>
                      </div>
                      <div className="h-1.5 rounded-full bg-muted overflow-hidden">
                        <div
                          className="h-full rounded-full bg-primary transition-all"
                          style={{ width: `${progress.percent}%` }}
                        />
                      </div>
                    </div>
                  )}

                  {/* Currently Processing */}
                  {isRunning && processing && processing.length > 0 && (
                    <div className="space-y-1">
                      <p className="text-xs text-muted-foreground">
                        Currently processing:
                      </p>
                      <div className="space-y-1">
                        {processing.slice(0, 3).map((item) => (
                          <div
                            key={item.id}
                            className="flex items-center justify-between text-sm rounded-md bg-muted/50 px-2 py-1"
                          >
                            <span className="truncate">{item.name}</span>
                            <Loader2 className="h-3 w-3 animate-spin text-muted-foreground flex-shrink-0" />
                          </div>
                        ))}
                        {processing.length > 3 && (
                          <p className="text-xs text-muted-foreground px-2">
                            +{processing.length - 3} more
                          </p>
                        )}
                      </div>
                    </div>
                  )}
                </div>
              )
            })}
          </CardContent>
        </Card>

        {/* Error / DLQ Summary */}
        <Card>
          <CardHeader className="flex flex-row items-center justify-between">
            <CardTitle className="flex items-center gap-2">
              <ShieldAlert className="h-5 w-5 text-destructive" />
              Error &amp; DLQ Summary
            </CardTitle>
            <Link href="/errors">
              <Button variant="ghost" size="sm">
                View Details
              </Button>
            </Link>
          </CardHeader>
          <CardContent className="space-y-4">
            {errorStats ? (
              <>
                <div className="grid grid-cols-2 gap-3">
                  <div className="rounded-lg border p-3">
                    <p className="text-xs text-muted-foreground">Quarantined</p>
                    <p className="text-xl font-bold">
                      {errorStats.dlq?.total_quarantined ?? 0}
                    </p>
                  </div>
                  <div className="rounded-lg border p-3">
                    <p className="text-xs text-muted-foreground">Expiring Soon</p>
                    <p className="text-xl font-bold">
                      {errorStats.dlq?.expiring_soon ?? 0}
                    </p>
                  </div>
                </div>

                {errorStats.dlq?.by_category &&
                  Object.keys(errorStats.dlq.by_category).length > 0 && (
                    <div className="space-y-1">
                      <p className="text-xs text-muted-foreground">
                        By Category
                      </p>
                      <div className="flex flex-wrap gap-2">
                        {Object.entries(errorStats.dlq.by_category).map(
                          ([category, count]) => (
                            <Badge key={category} variant="secondary">
                              {category}: {count}
                            </Badge>
                          )
                        )}
                      </div>
                    </div>
                  )}

                {errorStats.circuit_breakers &&
                  Object.keys(errorStats.circuit_breakers).length > 0 && (
                    <div className="space-y-1">
                      <p className="text-xs text-muted-foreground">
                        Circuit Breakers
                      </p>
                      <div className="flex flex-wrap gap-2">
                        {Object.entries(errorStats.circuit_breakers).map(
                          ([name, metrics]: [string, any]) => (
                            <Badge
                              key={name}
                              variant="outline"
                              className={cn(
                                metrics.state === 'open' &&
                                  'border-red-500 text-red-600 bg-red-50 dark:bg-red-950/20',
                                metrics.state === 'half_open' &&
                                  'border-yellow-500 text-yellow-600 bg-yellow-50 dark:bg-yellow-950/20',
                                metrics.state === 'closed' &&
                                  'border-green-500 text-green-600 bg-green-50 dark:bg-green-950/20'
                              )}
                            >
                              {name}: {metrics.state}
                            </Badge>
                          )
                        )}
                      </div>
                    </div>
                  )}
              </>
            ) : (
              <div className="text-sm text-muted-foreground py-4 text-center">
                Loading error data...
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Two-column layout for Recent Activity + Recent Pending */}
      <div className="grid gap-6 lg:grid-cols-2">
        {/* Recent Job Activity */}
        <Card>
          <CardHeader className="flex flex-row items-center justify-between">
            <CardTitle>Recent Activity</CardTitle>
            <Link href="/jobs">
              <Button variant="ghost" size="sm">
                View All
              </Button>
            </Link>
          </CardHeader>
          <CardContent>
            {jobActivity && jobActivity.items.length > 0 ? (
              <div className="space-y-2">
                {jobActivity.items.map((item) => (
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
            ) : (
              <p className="text-muted-foreground text-center py-4">
                No recent activity
              </p>
            )}

            {/* Activity Pagination */}
            {jobActivity && jobActivity.items.length >= activityLimit && (
              <div className="flex items-center justify-between mt-4 pt-4 border-t">
                <Button
                  variant="outline"
                  size="sm"
                  disabled={activityOffset === 0}
                  onClick={() => setActivityOffset(Math.max(0, activityOffset - activityLimit))}
                >
                  Previous
                </Button>
                <span className="text-xs text-muted-foreground">
                  Page {Math.floor(activityOffset / activityLimit) + 1}
                </span>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setActivityOffset(activityOffset + activityLimit)}
                >
                  Next
                </Button>
              </div>
            )}
          </CardContent>
        </Card>

        {/* Recent Pending Actions */}
        <Card>
          <CardHeader className="flex flex-row items-center justify-between">
            <CardTitle>Recent Pending Actions</CardTitle>
            <Link href="/pending">
              <Button variant="ghost" size="sm">
                View All
              </Button>
            </Link>
          </CardHeader>
          <CardContent>
            {pending && pending.length > 0 ? (
              <div className="space-y-2">
                {pending.map((item) => (
                  <div
                    key={item.festival_id}
                    className="flex items-center justify-between rounded-lg border p-3"
                  >
                    <div className="flex items-center gap-3">
                      <div
                        className={`w-2 h-2 rounded-full ${getStateColor(
                          item.state
                        )}`}
                      />
                      <div>
                        <p className="font-medium">{item.name}</p>
                        <p className="text-sm text-muted-foreground">
                          {getStateLabel(item.state)} •{' '}
                          {formatRelativeTime(item.created_at)}
                        </p>
                      </div>
                    </div>
                    <Badge variant="outline">{item.suggested_action}</Badge>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-muted-foreground text-center py-4">
                No pending actions
              </p>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Thread Stream Modal */}
      {selectedThreadId && (
        <ThreadStreamModal
          threadId={selectedThreadId}
          onClose={() => setSelectedThreadId(null)}
        />
      )}
    </div>
  )
}
