'use client'

import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { JobPanel } from '@/components/jobs/JobPanel'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Activity, Zap, Search, RefreshCw, Database } from 'lucide-react'

export default function JobsPage() {
  const [activeTab, setActiveTab] = useState('overview')

  return (
    <div className="flex h-[calc(100vh-6rem)] flex-col space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-3xl font-bold">Job Control Center</h1>
      </div>

      <Tabs value={activeTab} onValueChange={setActiveTab} className="flex flex-1 flex-col">
        <TabsList className="grid w-full grid-cols-5">
          <TabsTrigger value="overview" className="flex items-center gap-2">
            <Activity className="h-4 w-4" />
            Overview
          </TabsTrigger>
          <TabsTrigger value="discovery" className="flex items-center gap-2">
            <Search className="h-4 w-4" />
            Discovery
          </TabsTrigger>
          <TabsTrigger value="research" className="flex items-center gap-2">
            <Zap className="h-4 w-4" />
            Research
          </TabsTrigger>
          <TabsTrigger value="sync" className="flex items-center gap-2">
            <RefreshCw className="h-4 w-4" />
            Sync
          </TabsTrigger>
          <TabsTrigger value="goabase" className="flex items-center gap-2">
            <Database className="h-4 w-4" />
            Goabase
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

        {/* Goabase Tab - Standard Job Panel */}
        <TabsContent value="goabase" className="flex-1">
          <JobPanel jobType="goabase" showStream={false} />
        </TabsContent>
      </Tabs>
    </div>
  )
}

// Interface for job status data (matches JobPanel.tsx)
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

interface AllJobStatus {
  goabase_sync?: JobStatus | null
  goabase?: JobStatus | null
  discovery?: JobStatus | null
  research?: JobStatus | null
  sync?: JobStatus | null
  refresh?: JobStatus | null
}

// Hook to fetch all job statuses at once
function useAllJobStatuses() {
  const { data, refetch } = useQuery({
    queryKey: ['all-job-statuses'],
    queryFn: async (): Promise<AllJobStatus> => {
      const response = await fetch('/api/jobs/status')
      if (!response.ok) throw new Error('Failed to fetch job status')
      return response.json()
    },
    refetchInterval: 2000,
  })
  return { data, refetch }
}

function JobOverview() {
  const { data: allStatuses } = useAllJobStatuses()

  // Helper function to get status data for a job type
  const getStatusData = (jobType: keyof AllJobStatus): JobStatus => {
    const status = allStatuses?.[jobType]
    return status || { status: 'idle' }
  }

  // Job display configuration
  const jobConfigs = [
    { type: 'discovery' as keyof AllJobStatus, displayName: 'Discovery' },
    { type: 'research' as keyof AllJobStatus, displayName: 'Research' },
    { type: 'sync' as keyof AllJobStatus, displayName: 'Sync' },
    { type: 'goabase' as keyof AllJobStatus, displayName: 'Goabase Sync' },
  ]

  return (
    <div className="grid h-full grid-cols-2 gap-4">
      <Card>
        <CardHeader>
          <CardTitle>All Jobs Status</CardTitle>
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

      <Card>
        <CardHeader>
          <CardTitle>Recent Activity</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="text-sm text-muted-foreground">
            No recent activity
          </div>
        </CardContent>
      </Card>
    </div>
  )
}

function JobStatusRow({ name, statusData }: { name: string; statusData: JobStatus }) {
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
