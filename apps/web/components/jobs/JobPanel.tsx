'use client'

import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { AgentStream } from '@/components/agents/AgentStream'
import { ThreadList } from '@/components/agents/ThreadList'
import { AgentStreamDrawer } from './AgentStreamDrawer'
import {
  startDiscoveryJob,
  stopDiscoveryJob,
  startResearchJob,
  stopResearchJob,
  startSyncJob,
  stopSyncJob,
  startGoabaseJob,
  stopGoabaseJob,
  getJobsStatus,
} from '@/lib/api'
import { useJobWebSocket } from '@/lib/hooks/use-job-websocket'
import type { JobStatusDetail } from '@/types'
import { Loader2, Play, Square, CheckCircle, XCircle, Clock, Eye } from 'lucide-react'
import { cn, formatRelativeTime } from '@/lib/utils'
import { useToast } from '@/components/ui/toast-provider'
import { JobStream } from './JobStream'

interface JobPanelProps {
  jobType: 'discovery' | 'research' | 'sync' | 'goabase'
  showStream: boolean
}

export function JobPanel({ jobType, showStream }: JobPanelProps) {
  const [selectedThread, setSelectedThread] = useState<string | null>(null)
  const [isStarting, setIsStarting] = useState(false)
  const [isStopping, setIsStopping] = useState(false)
  const [inspectorFestivalId, setInspectorFestivalId] = useState<string | null>(null)
  const { success } = useToast()

  // Real-time WebSocket + REST fallback
  const { statuses: wsStatuses } = useJobWebSocket()
  const { data: restStatuses } = useQuery({
    queryKey: ['job-status', jobType],
    queryFn: getJobsStatus,
    refetchInterval: 5000,
  })

  const allStatuses = wsStatuses || restStatuses
  const status = allStatuses?.[jobType]
  const isRunning = status?.status === 'running'

  const handleStart = async () => {
    setIsStarting(true)
    try {
      let result
      switch (jobType) {
        case 'discovery':
          result = await startDiscoveryJob()
          break
        case 'goabase':
          result = await startGoabaseJob()
          break
        case 'research':
          await startResearchJob()
          break
        case 'sync':
          await startSyncJob()
          break
        default:
          throw new Error(`Unknown job type: ${jobType}`)
      }

      // If we got a thread_id, select it to show the stream
      if (result?.thread_id) {
        setSelectedThread(result.thread_id)
      }

      success(`${jobType} job started`)
    } catch {
      // Error toast handled by API interceptor
    } finally {
      setIsStarting(false)
    }
  }

  const handleStop = async () => {
    setIsStopping(true)
    try {
      switch (jobType) {
        case 'discovery':
          await stopDiscoveryJob()
          break
        case 'goabase':
          await stopGoabaseJob()
          break
        case 'research':
          await stopResearchJob()
          break
        case 'sync':
          await stopSyncJob()
          break
        default:
          throw new Error(`Unknown job type: ${jobType}`)
      }
      success(`${jobType} job stopped`)
    } catch {
      // Error toast handled by API interceptor
    } finally {
      setIsStopping(false)
    }
  }

  return (
    <div className="grid h-full grid-cols-3 gap-4">
      {/* Left: Job Controls & Thread List */}
      <div className="col-span-1 flex flex-col gap-4 overflow-auto">
        <JobControlCard
          jobType={jobType}
          status={status}
          isRunning={isRunning}
          isStarting={isStarting}
          isStopping={isStopping}
          onStart={handleStart}
          onStop={handleStop}
        />

        {showStream && (
          <ThreadList
            agentType={jobType as 'research' | 'discovery' | 'goabase'}
            selectedThread={selectedThread}
            onSelectThread={setSelectedThread}
          />
        )}

        <ProcessingFestivals jobType={jobType} status={status} onInspect={setInspectorFestivalId} />
      </div>

      {/* Right: Job Stream or Job Status */}
      <div className="col-span-2 overflow-hidden rounded-lg border">
        {showStream && selectedThread ? (
          jobType === 'research' ? (
            <AgentStream threadId={selectedThread} />
          ) : (
            <JobStream threadId={selectedThread} jobType={jobType} />
          )
        ) : (
          <JobStatusPanel jobType={jobType} status={status} />
        )}
      </div>

      <AgentStreamDrawer
        open={!!inspectorFestivalId}
        onClose={() => setInspectorFestivalId(null)}
        festivalId={inspectorFestivalId}
        jobType={jobType}
      />
    </div>
  )
}

interface JobControlCardProps {
  jobType: string
  status?: JobStatusDetail
  isRunning: boolean
  isStarting: boolean
  isStopping: boolean
  onStart: () => void
  onStop: () => void
}

function JobControlCard({
  jobType,
  status,
  isRunning,
  isStarting,
  isStopping,
  onStart,
  onStop,
}: JobControlCardProps) {
  const getStatusIcon = () => {
    switch (status?.status) {
      case 'running':
        return <Loader2 className="h-5 w-5 animate-spin text-green-500" />
      case 'completed':
        return <CheckCircle className="h-5 w-5 text-blue-500" />
      case 'failed':
        return <XCircle className="h-5 w-5 text-destructive" />
      default:
        return <Clock className="h-5 w-5 text-muted-foreground" />
    }
  }

  const getStatusText = () => {
    switch (status?.status) {
      case 'running':
        return 'Running'
      case 'completed':
        return 'Completed'
      case 'failed':
        return 'Failed'
      default:
        return 'Idle'
    }
  }

  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="flex items-center justify-between text-base capitalize">
          {jobType} Job
          <Badge
            variant={isRunning ? 'default' : 'secondary'}
            className={cn(isRunning && 'bg-green-500')}
          >
            {getStatusIcon()}
            <span className="ml-1">{getStatusText()}</span>
          </Badge>
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Progress */}
        {status?.progress && (
          <div className="space-y-2">
            <div className="flex justify-between text-sm">
              <span className="text-muted-foreground">Progress</span>
              <span>
                {status.progress.current} / {status.progress.total}
              </span>
            </div>
            <div className="h-2 rounded-full bg-muted">
              <div
                className="h-full rounded-full bg-primary transition-all"
                style={{ width: `${status.progress.percent}%` }}
              />
            </div>
          </div>
        )}

        {/* Controls */}
        <div className="flex gap-2">
          {!isRunning ? (
            <Button
              onClick={onStart}
              disabled={isStarting}
              className="flex-1"
            >
              {isStarting ? (
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              ) : (
                <Play className="mr-2 h-4 w-4" />
              )}
              Start
            </Button>
          ) : (
            <Button
              onClick={onStop}
              disabled={isStopping}
              variant="destructive"
              className="flex-1"
            >
              {isStopping ? (
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              ) : (
                <Square className="mr-2 h-4 w-4" />
              )}
              Stop
            </Button>
          )}
        </div>
      </CardContent>
    </Card>
  )
}

function ProcessingFestivals({
  jobType,
  status,
  onInspect,
}: {
  jobType: string
  status?: JobStatusDetail
  onInspect?: (festivalId: string) => void
}) {
  const processing = status?.currently_processing

  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="text-sm font-medium">Processing</CardTitle>
      </CardHeader>
      <CardContent>
        {processing && processing.length > 0 ? (
          <div className="space-y-2">
            {processing.slice(0, 5).map((item) => (
              <div
                key={item.id}
                className="flex items-center justify-between text-sm rounded-md bg-muted/50 px-2 py-1 group"
              >
                <span className="truncate">{item.name}</span>
                <div className="flex items-center gap-2">
                  {onInspect && (
                    <button
                      onClick={() => onInspect(item.id)}
                      className="opacity-0 group-hover:opacity-100 transition-opacity p-1 rounded hover:bg-muted"
                      title="Inspect stream"
                    >
                      <Eye className="h-3 w-3 text-muted-foreground" />
                    </button>
                  )}
                  <Loader2 className="h-3 w-3 animate-spin text-muted-foreground flex-shrink-0" />
                </div>
              </div>
            ))}
            {processing.length > 5 && (
              <p className="text-xs text-muted-foreground px-2">
                +{processing.length - 5} more
              </p>
            )}
          </div>
        ) : (
          <div className="text-sm text-muted-foreground">
            No festivals currently processing
          </div>
        )}
      </CardContent>
    </Card>
  )
}

interface JobStatusPanelProps {
  jobType: string
  status?: JobStatusDetail
}

function JobStatusPanel({ jobType, status }: JobStatusPanelProps) {
  return (
    <div className="flex h-full flex-col p-6">
      <h3 className="mb-4 text-lg font-medium capitalize">{jobType} Status</h3>
      {status?.currently_processing && status.currently_processing.length > 0 ? (
        <div className="space-y-2">
          {status.currently_processing.map((item) => (
            <div
              key={item.id}
              className="flex items-center justify-between rounded-md border p-3"
            >
              <span className="font-medium">{item.name}</span>
              <div className="flex items-center gap-2 text-xs text-muted-foreground">
                <Loader2 className="h-4 w-4 animate-spin" />
                {formatRelativeTime(item.started_at)}
              </div>
            </div>
          ))}
        </div>
      ) : (
        <div className="flex h-full items-center justify-center text-muted-foreground">
          {status?.status === 'running'
            ? 'Job is running...'
            : 'No active processing'}
        </div>
      )}
    </div>
  )
}
