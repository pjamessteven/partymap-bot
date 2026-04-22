'use client'

import { useQuery } from '@tanstack/react-query'
import { getStats, getPendingFestivals, getJobsStatus } from '@/lib/api'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { formatCurrency, getStateColor, getStateLabel, formatRelativeTime, cn } from '@/lib/utils'
import {
  Music,
  DollarSign,
  AlertCircle,
  CheckCircle,
  Clock,
  RefreshCw,
  Activity,
  Play,
  StopCircle,
} from 'lucide-react'
import Link from 'next/link'
import { useState } from 'react'
import { runDiscovery } from '@/lib/api'
import { useToast } from '@/components/ui/toast-provider'
import { StateBadge } from '@/components/state-badge'

export default function DashboardPage() {
  const [isRunningDiscovery, setIsRunningDiscovery] = useState(false)
  const { success, error } = useToast()

  const { data: stats, refetch: refetchStats } = useQuery({
    queryKey: ['stats'],
    queryFn: getStats,
  })

  const { data: pending } = useQuery({
    queryKey: ['pending', 5],
    queryFn: () => getPendingFestivals(undefined, 5),
  })

  const { data: jobs } = useQuery({
    queryKey: ['jobs'],
    queryFn: getJobsStatus,
  })

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

  const stateOrder = ['discovered', 'researching', 'researched', 'syncing', 'synced', 'failed', 'skipped']

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-3xl font-bold">Dashboard</h1>
        <Button
          onClick={handleRunDiscovery}
          disabled={isRunningDiscovery}
          className="gap-2"
        >
          <RefreshCw className={cn('h-4 w-4', isRunningDiscovery && 'animate-spin')} />
          Run Discovery
        </Button>
      </div>

      {/* Stats Grid */}
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
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

      {/* State Distribution */}
      <Card>
        <CardHeader>
          <CardTitle>Festival States</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex flex-wrap gap-2">
            {stats?.by_state && stateOrder.map((state) => {
              const count = stats.by_state[state as keyof typeof stats.by_state] ?? 0
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

      {/* Jobs Status */}
      <Card>
        <CardHeader className="flex flex-row items-center justify-between">
          <CardTitle>Active Jobs</CardTitle>
          <Link href="/jobs">
            <Button variant="ghost" size="sm">Manage Jobs</Button>
          </Link>
        </CardHeader>
        <CardContent>
          <div className="grid gap-4 md:grid-cols-4">
            {['discovery', 'research', 'sync', 'goabase'].map((jobType) => {
              const job = jobs?.[jobType]
              const isRunning = job?.status === 'running'
              return (
                <div key={jobType} className="flex items-center justify-between rounded-lg border p-3">
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
              )
            })}
          </div>
        </CardContent>
      </Card>

      {/* Recent Pending Actions */}
      <Card>
        <CardHeader className="flex flex-row items-center justify-between">
          <CardTitle>Recent Pending Actions</CardTitle>
          <Link href="/pending">
            <Button variant="ghost" size="sm">View All</Button>
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
                    <div className={`w-2 h-2 rounded-full ${getStateColor(item.state)}`} />
                    <div>
                      <p className="font-medium">{item.name}</p>
                      <p className="text-sm text-muted-foreground">
                        {getStateLabel(item.state)} • {formatRelativeTime(item.created_at)}
                      </p>
                    </div>
                  </div>
                  <Badge variant="outline">{item.suggested_action}</Badge>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-muted-foreground text-center py-4">No pending actions</p>
          )}
        </CardContent>
      </Card>
    </div>
  )
}


