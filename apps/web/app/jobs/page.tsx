'use client'

import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { JobPanel } from '@/components/jobs/JobPanel'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { getJobsStatus } from '@/lib/api'
import type { JobStatus } from '@/types'
import { Activity, Zap, Search, RefreshCw, Database } from 'lucide-react'
import { useDocumentVisibility } from '@/lib/hooks/use-document-visibility'

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
        <h1 className="text-3xl font-bold">Job Control Center</h1>
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

        {/* Goabase Tab - Standard Job Panel */}
        <TabsContent value="goabase" className="flex-1">
          <JobPanel jobType="goabase" showStream={false} />
        </TabsContent>
      </Tabs>
    </div>
  )
}

function JobOverview() {
  const isVisible = useDocumentVisibility()
  const { data: allStatuses } = useQuery({
    queryKey: ['all-job-statuses'],
    queryFn: getJobsStatus,
    refetchInterval: isVisible ? 2000 : false,
  })

  // Helper function to get status data for a job type
  const getStatusData = (jobType: string): SimpleJobStatus => {
    const status = allStatuses?.[jobType]
    return status || { status: 'idle' }
  }

  // Job display configuration
  const jobConfigs = [
    { type: 'discovery', displayName: 'Discovery' },
    { type: 'research', displayName: 'Research' },
    { type: 'sync', displayName: 'Sync' },
    { type: 'goabase', displayName: 'Goabase Sync' },
  ]

  return (
    <div className="grid h-full grid-cols-1 md:grid-cols-2 gap-4">
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

function JobStatusRow({ name, statusData }: { name: string; statusData: SimpleJobStatus }) {
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
