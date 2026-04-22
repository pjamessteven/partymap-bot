'use client'

import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { AgentStream } from '@/components/agents/AgentStream'
import { ThreadList } from '@/components/agents/ThreadList'
import { Loader2, Play, Square, RefreshCw, CheckCircle, XCircle, Clock } from 'lucide-react'
import { cn } from '@/lib/utils'

interface JobPanelProps {
  jobType: 'discovery' | 'research' | 'sync' | 'goabase'
  showStream: boolean
}

interface JobStatus {
  status: 'idle' | 'running' | 'completed' | 'failed'
  task_id?: string
  started_at?: string
  progress?: {
    current: number
    total: number
    percent: number
  }
  currently_processing?: Array<{
    id: string
    name: string
    started_at: string
  }>
}

export function JobPanel({ jobType, showStream }: JobPanelProps) {
  const [selectedThread, setSelectedThread] = useState<string | null>(null)
  const [isStarting, setIsStarting] = useState(false)
  const [isStopping, setIsStopping] = useState(false)

  // Fetch job status
  const { data: status, refetch } = useJobStatus(jobType)

  const handleStart = async () => {
    setIsStarting(true)
    try {
      let response
      switch (jobType) {
        case 'discovery':
          response = await fetch('/api/jobs/discovery/start', { method: 'POST' })
          break
        case 'goabase':
          response = await fetch('/api/jobs/goabase/start', { method: 'POST' })
          break
        case 'research':
          response = await fetch('/api/jobs/research/start', { method: 'POST' })
          break
        case 'sync':
          response = await fetch('/api/jobs/sync/start', { method: 'POST' })
          break
        default:
          throw new Error(`Unknown job type: ${jobType}`)
      }
      if (!response.ok) throw new Error('Failed to start job')
      await refetch()
    } catch (error) {
      console.error('Failed to start job:', error)
    } finally {
      setIsStarting(false)
    }
  }

  const handleStop = async () => {
    setIsStopping(true)
    try {
      let response
      switch (jobType) {
        case 'discovery':
          response = await fetch('/api/jobs/discovery/stop', { method: 'POST' })
          break
        case 'goabase':
          response = await fetch('/api/jobs/goabase/stop', { method: 'POST' })
          break
        case 'research':
          response = await fetch('/api/jobs/research/stop', { method: 'POST' })
          break
        case 'sync':
          response = await fetch('/api/jobs/sync/stop', { method: 'POST' })
          break
        default:
          throw new Error(`Unknown job type: ${jobType}`)
      }
      if (!response.ok) throw new Error('Failed to stop job')
      await refetch()
    } catch (error) {
      console.error('Failed to stop job:', error)
    } finally {
      setIsStopping(false)
    }
  }

  const isRunning = status?.status === 'running'

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
            agentType={jobType as 'research' | 'discovery'}
            selectedThread={selectedThread}
            onSelectThread={setSelectedThread}
          />
        )}

        <ProcessingFestivals jobType={jobType} />
      </div>

      {/* Right: Agent Stream or Job Status */}
      <div className="col-span-2 overflow-hidden rounded-lg border">
        {showStream ? (
          <AgentStream threadId={selectedThread} />
        ) : (
          <JobStatusPanel jobType={jobType} status={status} />
        )}
      </div>
    </div>
  )
}

interface JobControlCardProps {
  jobType: string
  status?: JobStatus
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

function ProcessingFestivals({ jobType }: { jobType: string }) {
  // This would fetch currently processing festivals for this job type
  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="text-sm font-medium">Processing</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="text-sm text-muted-foreground">
          No festivals currently processing
        </div>
      </CardContent>
    </Card>
  )
}

interface JobStatusPanelProps {
  jobType: string
  status?: JobStatus
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
              <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
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

// Hook for fetching job status
function useJobStatus(jobType: string) {
  const { data, refetch } = useQuery({
    queryKey: ['job-status', jobType],
    queryFn: async (): Promise<JobStatus> => {
      const response = await fetch('/api/jobs/status')
      if (!response.ok) throw new Error('Failed to fetch job status')
      const statuses = await response.json()
      return statuses[jobType] || { status: 'idle' }
    },
    refetchInterval: 2000,
  })

  return { data, refetch }
}
