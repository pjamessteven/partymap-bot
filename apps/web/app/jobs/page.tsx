'use client'

import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import dynamic from 'next/dynamic'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import {
  getJobsStatus,
  getJobActivity,
  startJobsBulk,
  stopJobsBulk,
} from '@/lib/api'
import { useJobWebSocket } from '@/lib/hooks/use-job-websocket'
import { useToast } from '@/components/ui/toast-provider'
import type { JobStatus } from '@/types'
import {
  Activity,
  Zap,
  Search,
  RefreshCw,
  Database,
  Play,
  Square,
  Loader2,
} from 'lucide-react'
import { formatRelativeTime, cn } from '@/lib/utils'
import { GoabaseSyncPanel } from '@/components/GoabaseSyncPanel'

const JobPanel = dynamic(
  () => import('@/components/jobs/JobPanel').then((mod) => mod.JobPanel),
  { ssr: false }
)

interface SimpleJobStatus {
  status: string
  task_id?: string
  started_at?: string
  progress?: {
    current: number
    total: number
    percent: number
  }
}

export default function JobsPage() {
  const [activeTab, setActiveTab] = useState('overview')

  return (
    <div className="flex h-[calc(100vh-6rem)] flex-col space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl sm:text-3xl font-bold">Job Control Center</h1>
      </div>

      <Tabs value={activeTab} onValueChange={setActiveTab} className="flex flex-1 flex-col">
        <TabsList className="grid w-full grid-cols-5">
          <TabsTrigger value="overview" className="px-1 sm:px-3">
            <Activity className="h-4 w-4 sm:mr-2" />
            <span className="hidden sm:inline">Overview</span>
          </TabsTrigger>
          <TabsTrigger value="discovery" className="px-1 sm:px-3">
            <Search className="h-4 w-4 sm:mr-2" />
            <span className="hidden sm:inline">Discovery</span>
          </TabsTrigger>
          <TabsTrigger value="research" className="px-1 sm:px-3">
            <Zap className="h-4 w-4 sm:mr-2" />
            <span className="hidden sm:inline">Research</span>
          </TabsTrigger>
          <TabsTrigger value="sync" className="px-1 sm:px-3">
            <RefreshCw className="h-4 w-4 sm:mr-2" />
            <span className="hidden sm:inline">Sync</span>
          </TabsTrigger>
          <TabsTrigger value="goabase" className="px-1 sm:px-3">
            <Database className="h-4 w-4 sm:mr-2" />
            <span className="hidden sm:inline">Goabase</span>
          </TabsTrigger>
        </TabsList>

        {/* Overview Tab */}
        <TabsContent value="overview" className="flex-1">
          <JobOverview />
        </TabsContent>

        {/* Discovery Tab - With AI Elements Stream */}
        <TabsContent value="discovery" className="flex-1">
          <JobPanel jobType="discovery" showStream={true} />
        </TabsContent>

        {/* Research Tab - With AI Elements Stream */}
        <TabsContent value="research" className="flex-1">
          <JobPanel jobType="research" showStream={true} />
        </TabsContent>

        {/* Sync Tab - Standard Job Panel */}
        <TabsContent value="sync" className="flex-1">
          <JobPanel jobType="sync" showStream={false} />
        </TabsContent>

        {/* Goabase Tab - With AI Elements Stream */}
        <TabsContent value="goabase" className="flex-1">
          <div className="grid h-full grid-cols-3 gap-4">
            <div className="col-span-2">
              <JobPanel jobType="goabase" showStream={true} />
            </div>
            <div className="col-span-1 overflow-auto">
              <GoabaseSyncPanel />
            </div>
          </div>
        </TabsContent>
      </Tabs>
    </div>
  )
}

function JobOverview() {
  const { statuses: wsStatuses } = useJobWebSocket()
  const queryClient = useQueryClient()
  const { success, error } = useToast()

  const { data: allStatusesRest } = useQuery({
    queryKey: ['all-job-statuses'],
    queryFn: getJobsStatus,
    refetchInterval: 5000,
  })

  const { data: activity } = useQuery({
    queryKey: ['job-activity', 20],
    queryFn: () => getJobActivity(undefined, 20),
    refetchInterval: 5000,
  })

  const allStatuses = wsStatuses || allStatusesRest

  const startBulkMutation = useMutation({
    mutationFn: (jobTypes: string[]) => startJobsBulk(jobTypes),
    onSuccess: (data) => {
      const succeeded = data.results.filter((r) => r.success).length
      success(`Started ${succeeded} job(s)`)
      queryClient.invalidateQueries({ queryKey: ['all-job-statuses'] })
      queryClient.invalidateQueries({ queryKey: ['job-status'] })
    },
  })

  const stopBulkMutation = useMutation({
    mutationFn: (jobTypes: string[]) => stopJobsBulk(jobTypes),
    onSuccess: (data) => {
      const succeeded = data.results.filter((r) => r.success).length
      success(`Stopped ${succeeded} job(s)`)
      queryClient.invalidateQueries({ queryKey: ['all-job-statuses'] })
      queryClient.invalidateQueries({ queryKey: ['job-status'] })
    },
  })

  // Helper function to get status data for a job type
  const getStatusData = (jobType: string): SimpleJobStatus => {
    const status = allStatuses?.[jobType]
    return status || { status: 'idle' }
  }

  const jobConfigs = [
    { type: 'discovery', displayName: 'Discovery' },
    { type: 'research', displayName: 'Research' },
    { type: 'sync', displayName: 'Sync' },
    { type: 'goabase', displayName: 'Goabase Sync' },
  ]

  const idleJobs = jobConfigs
    .filter((j) => getStatusData(j.type).status !== 'running')
    .map((j) => j.type)

  const runningJobs = jobConfigs
    .filter((j) => getStatusData(j.type).status === 'running')
    .map((j) => j.type)

  return (
    <div className="grid h-full grid-cols-1 md:grid-cols-2 gap-4">
      <div className="space-y-4">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between">
            <CardTitle>All Jobs Status</CardTitle>
            <div className="flex gap-2">
              {idleJobs.length > 0 && (
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => startBulkMutation.mutate(idleJobs)}
                  disabled={startBulkMutation.isPending}
                >
                  {startBulkMutation.isPending ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : (
                    <Play className="h-4 w-4" />
                  )}
                  <span className="ml-1 hidden sm:inline">Start All</span>
                </Button>
              )}
              {runningJobs.length > 0 && (
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => stopBulkMutation.mutate(runningJobs)}
                  disabled={stopBulkMutation.isPending}
                >
                  {stopBulkMutation.isPending ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : (
                    <Square className="h-4 w-4" />
                  )}
                  <span className="ml-1 hidden sm:inline">Stop All</span>
                </Button>
              )}
            </div>
          </CardHeader>
          <CardContent>
            <div className="space-y-4">
              {jobConfigs.map((job) => (
                <JobStatusRow
                  key={job.type}
                  name={job.displayName}
                  statusData={getStatusData(job.type)}
                />
              ))}
            </div>
          </CardContent>
        </Card>
      </div>

      <Card className="flex flex-col">
        <CardHeader>
          <CardTitle>Recent Activity</CardTitle>
        </CardHeader>
        <CardContent className="flex-1 overflow-auto">
          {activity && activity.items.length > 0 ? (
            <div className="space-y-2">
              {activity.items.map((item) => (
                <div
                  key={item.id}
                  className="flex items-center justify-between rounded-lg border p-3"
                >
                  <div className="flex items-center gap-3 min-w-0">
                    <Badge variant="outline" className="capitalize flex-shrink-0">
                      {item.job_type}
                    </Badge>
                    <div className="min-w-0">
                      <p className="text-sm font-medium truncate">{item.message}</p>
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
            <div className="text-sm text-muted-foreground text-center py-8">
              No recent activity
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  )
}

function JobStatusRow({
  name,
  statusData,
}: {
  name: string
  statusData: SimpleJobStatus
}) {
  const status = statusData.status

  const getStatusColor = () => {
    switch (status) {
      case 'running':
        return 'text-green-500'
      case 'completed':
        return 'text-blue-500'
      case 'failed':
        return 'text-destructive'
      default:
        return 'text-muted-foreground'
    }
  }

  const showProgress = status === 'running' && statusData?.progress

  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between">
        <span className="font-medium">{name}</span>
        <span className={`text-sm capitalize ${getStatusColor()}`}>{status}</span>
      </div>
      {showProgress && (
        <div className="space-y-1">
          <div className="flex justify-between text-xs">
            <span className="text-muted-foreground">Progress</span>
            <span>
              {statusData.progress?.current} / {statusData.progress?.total}
            </span>
          </div>
          <div className="h-1 rounded-full bg-muted">
            <div
              className="h-full rounded-full bg-primary transition-all"
              style={{ width: `${statusData.progress?.percent}%` }}
            />
          </div>
        </div>
      )}
    </div>
  )
}
