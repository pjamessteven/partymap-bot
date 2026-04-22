'use client'

import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { 
  getPipelineStatus, 
  startPipeline, 
  stopPipeline,
  getAllPipelineStatuses
} from '@/lib/api'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Progress } from '@/components/ui/progress'
import { Play, Square, RefreshCw, AlertCircle, CheckCircle } from 'lucide-react'

interface PipelineStatus {
  name: string
  description: string
  status: 'idle' | 'running' | 'stopping' | 'error'
  is_running: boolean
  can_start: boolean
  can_stop: boolean
  progress_percentage: number
  current_operation?: string
  total_items: number
  processed_items: number
  error_count: number
  last_error?: string
  started_at?: string
  completed_at?: string
}

const PIPELINES = [
  { key: 'discovery', name: 'Discovery', description: 'Search for new festivals via Exa' },
  { key: 'goabase_sync', name: 'Goabase Sync', description: 'Sync festivals from Goabase API' },
  { key: 'research', name: 'Research', description: 'Research festival details' },
  { key: 'sync', name: 'PartyMap Sync', description: 'Sync to PartyMap' },
  { key: 'deduplication', name: 'Deduplication', description: 'Check for duplicates' },
] as const

function PipelineCard({ 
  pipelineKey, 
  info 
}: { 
  pipelineKey: string
  info: PipelineStatus 
}) {
  const queryClient = useQueryClient()
  const [isHovered, setIsHovered] = useState(false)

  const startMutation = useMutation({
    mutationFn: () => startPipeline(pipelineKey),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['pipelines'] })
    },
  })

  const stopMutation = useMutation({
    mutationFn: () => stopPipeline(pipelineKey),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['pipelines'] })
    },
  })

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'running': return 'default'
      case 'stopping': return 'secondary'
      case 'error': return 'destructive'
      default: return 'outline'
    }
  }

  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'running': return <RefreshCw className="h-3 w-3 animate-spin" />
      case 'error': return <AlertCircle className="h-3 w-3" />
      case 'idle': return <CheckCircle className="h-3 w-3" />
      default: return null
    }
  }

  return (
    <Card 
      className="relative"
      onMouseEnter={() => setIsHovered(true)}
      onMouseLeave={() => setIsHovered(false)}
    >
      <CardHeader className="pb-2">
        <div className="flex items-start justify-between">
          <div>
            <CardTitle className="text-base">{info.name}</CardTitle>
            <p className="text-xs text-muted-foreground mt-1">
              {info.description}
            </p>
          </div>
          <Badge variant={getStatusColor(info.status)} className="flex items-center gap-1">
            {getStatusIcon(info.status)}
            {info.status}
          </Badge>
        </div>
      </CardHeader>
      
      <CardContent className="space-y-3">
        {/* Progress */}
        {info.is_running && (
          <div className="space-y-1">
            <Progress value={info.progress_percentage} className="h-2" />
            <div className="flex justify-between text-xs text-muted-foreground">
              <span>{info.current_operation || 'Processing...'}</span>
              <span>{info.progress_percentage}%</span>
            </div>
          </div>
        )}

        {/* Stats */}
        {(info.processed_items > 0 || info.total_items > 0) && (
          <div className="flex gap-4 text-xs">
            <span className="text-muted-foreground">
              Processed: <strong>{info.processed_items}</strong>
              {info.total_items > 0 && ` / ${info.total_items}`}
            </span>
            {info.error_count > 0 && (
              <span className="text-red-500">
                Errors: <strong>{info.error_count}</strong>
              </span>
            )}
          </div>
        )}

        {/* Last run */}
        {info.completed_at && !info.is_running && (
          <p className="text-xs text-muted-foreground">
            Last run: {new Date(info.completed_at).toLocaleString()}
          </p>
        )}

        {/* Error */}
        {info.last_error && (
          <p className="text-xs text-red-500 truncate" title={info.last_error}>
            Error: {info.last_error}
          </p>
        )}

        {/* Control Buttons */}
        <div className="flex justify-end gap-2 pt-2">
          {info.is_running ? (
            <Button
              variant="destructive"
              size="sm"
              onClick={() => stopMutation.mutate()}
              disabled={stopMutation.isPending || info.status === 'stopping'}
            >
              <Square className="h-3 w-3 mr-1" />
              {info.status === 'stopping' ? 'Stopping...' : 'Stop'}
            </Button>
          ) : (
            <Button
              variant="default"
              size="sm"
              onClick={() => startMutation.mutate()}
              disabled={startMutation.isPending || !info.can_start}
            >
              <Play className="h-3 w-3 mr-1" />
              Start
            </Button>
          )}
        </div>
      </CardContent>
    </Card>
  )
}

export function PipelineControlPanel() {
  const { data, isLoading } = useQuery({
    queryKey: ['pipelines'],
    queryFn: getAllPipelineStatuses,
    refetchInterval: 2000, // Poll every 2 seconds
  })

  if (isLoading) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Pipeline Control</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-muted-foreground">Loading pipeline statuses...</p>
        </CardContent>
      </Card>
    )
  }

  const pipelines = data?.pipelines || {}

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <div>
            <CardTitle>Pipeline Control</CardTitle>
            <p className="text-sm text-muted-foreground">
              Manual control of all services and pipelines
            </p>
          </div>
          <Badge variant="outline">
            {Object.values(pipelines).filter((p: any) => p.is_running).length} running
          </Badge>
        </div>
      </CardHeader>
      <CardContent>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {PIPELINES.map(({ key, name, description }) => {
            const info = pipelines[key] || {
              name,
              description,
              status: 'idle',
              is_running: false,
              can_start: true,
              can_stop: false,
              progress_percentage: 0,
              total_items: 0,
              processed_items: 0,
              error_count: 0,
            }
            return (
              <PipelineCard 
                key={key} 
                pipelineKey={key} 
                info={info as PipelineStatus}
              />
            )
          })}
        </div>
      </CardContent>
    </Card>
  )
}
