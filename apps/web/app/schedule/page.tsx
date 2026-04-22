'use client'

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  getSchedules,
  updateSchedule,
  enableSchedule,
  disableSchedule,
  applyScheduleChanges,
  runTaskNow,
} from '@/lib/api'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Select } from '@/components/ui/select'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { formatDate, formatRelativeTime } from '@/lib/utils'
import { useState } from 'react'
import { useToast } from '@/components/ui/toast-provider'
import {
  Check,
  X,
  Play,
  RefreshCw,
  Clock,
  Calendar,
  AlertCircle,
} from 'lucide-react'

const taskDescriptions: Record<string, string> = {
  discovery: 'Runs festival discovery using Exa and Goabase APIs',
  goabase_sync: 'Syncs festivals from Goabase API',
  cleanup_failed: 'Cleans up festivals stuck in failed state for 30+ days',
}

export default function SchedulePage() {
  const queryClient = useQueryClient()
  const [editing, setEditing] = useState<string | null>(null)
  const [editValues, setEditValues] = useState({
    hour: 0,
    minute: 0,
    day_of_week: '',
  })
  const [pageError, setPageError] = useState<string | null>(null)
  const [pageSuccess, setPageSuccess] = useState<string | null>(null)
  const { success: toastSuccess, error: toastError } = useToast()

  const { data: schedules, isLoading, refetch } = useQuery({
    queryKey: ['schedules'],
    queryFn: getSchedules,
  })

  const clearMessages = () => {
    setPageError(null)
    setPageSuccess(null)
  }

  const enableMutation = useMutation({
    mutationFn: enableSchedule,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['schedules'] })
      toastSuccess('Schedule enabled successfully')
    },
    onError: (err: Error) => {
      setPageError(err.message || 'Failed to enable schedule')
      toastError('Failed to enable schedule')
    },
  })

  const disableMutation = useMutation({
    mutationFn: disableSchedule,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['schedules'] })
      toastSuccess('Schedule disabled successfully')
    },
    onError: (err: Error) => {
      setPageError(err.message || 'Failed to disable schedule')
      toastError('Failed to disable schedule')
    },
  })

  const updateMutation = useMutation({
    mutationFn: ({ taskType, updates }: { taskType: string; updates: Parameters<typeof updateSchedule>[1] }) =>
      updateSchedule(taskType, updates),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['schedules'] })
      setEditing(null)
      toastSuccess('Schedule updated successfully')
    },
    onError: (err: Error) => {
      setPageError(err.message || 'Failed to update schedule')
      toastError('Failed to update schedule')
    },
  })

  const applyMutation = useMutation({
    mutationFn: applyScheduleChanges,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['schedules'] })
      toastSuccess('Schedule changes applied successfully')
    },
    onError: (err: Error) => {
      setPageError(err.message || 'Failed to apply schedule changes')
      toastError('Failed to apply schedule changes')
    },
  })

  const runNowMutation = useMutation({
    mutationFn: runTaskNow,
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['schedules'] })
      toastSuccess(`Task "${data.task_type}" started successfully`)
    },
    onError: (err: Error) => {
      setPageError(err.message || 'Failed to run task')
      toastError('Failed to run task')
    },
  })

  const startEditing = (schedule: NonNullable<typeof schedules>[number]) => {
    setEditing(schedule.task_type)
    setEditValues({
      hour: schedule.hour,
      minute: schedule.minute,
      day_of_week: schedule.day_of_week?.toString() ?? '',
    })
  }

  const saveEdit = (taskType: string) => {
    updateMutation.mutate({
      taskType,
      updates: {
        hour: editValues.hour,
        minute: editValues.minute,
        day_of_week: editValues.day_of_week
          ? parseInt(editValues.day_of_week)
          : undefined,
      },
    })
  }

  const formatSchedule = (schedule: NonNullable<typeof schedules>[number]) => {
    const days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
    const time = `${schedule.hour.toString().padStart(2, '0')}:${schedule.minute.toString().padStart(2, '0')}`

    if (schedule.day_of_week !== null && schedule.day_of_week !== undefined) {
      return `${days[schedule.day_of_week]} at ${time} UTC`
    }
    return `Daily at ${time} UTC`
  }

  if (isLoading) {
    return (
      <div className="space-y-6">
        <h1 className="text-3xl font-bold">Schedule</h1>
        <div className="text-center py-8">Loading...</div>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-3xl font-bold">Schedule</h1>
        <div className="flex gap-2">
          <Button
            onClick={() => applyMutation.mutate()}
            disabled={applyMutation.isPending}
            variant="outline"
          >
            <RefreshCw
              className={`h-4 w-4 mr-2 ${
                applyMutation.isPending ? 'animate-spin' : ''
              }`}
            />
            Apply Changes
          </Button>
        </div>
      </div>

      {pageError && (
        <Alert variant="destructive">
          <AlertCircle className="h-4 w-4" />
          <AlertTitle>Error</AlertTitle>
          <AlertDescription>{pageError}</AlertDescription>
        </Alert>
      )}

      {pageSuccess && (
        <Alert className="border-green-500 text-green-700">
          <Check className="h-4 w-4" />
          <AlertTitle>Success</AlertTitle>
          <AlertDescription>{pageSuccess}</AlertDescription>
        </Alert>
      )}

      <div className="grid gap-6">
        {schedules?.map((schedule) => (
          <Card key={schedule.task_type}>
            <CardContent className="pt-6">
              <div className="flex items-start justify-between">
                <div className="space-y-2">
                  <div className="flex items-center gap-3">
                    <h3 className="text-lg font-semibold capitalize">
                      {schedule.task_type.replace(/_/g, ' ')}
                    </h3>
                    <Badge
                      variant={schedule.enabled ? 'default' : 'secondary'}
                      className={
                        schedule.enabled ? 'bg-green-500 text-white' : ''
                      }
                    >
                      {schedule.enabled ? (
                        <>
                          <Check className="h-3 w-3 mr-1" /> Enabled
                        </>
                      ) : (
                        <>
                          <X className="h-3 w-3 mr-1" /> Disabled
                        </>
                      )}
                    </Badge>
                  </div>
                  <p className="text-sm text-muted-foreground">
                    {taskDescriptions[schedule.task_type] || 'No description'}
                  </p>

                  {editing === schedule.task_type ? (
                    <div className="flex items-center gap-2 mt-4">
                      <Clock className="h-4 w-4 text-muted-foreground" />
                      <Input
                        type="number"
                        min={0}
                        max={23}
                        value={editValues.hour}
                        onChange={(e) =>
                          setEditValues({
                            ...editValues,
                            hour: parseInt(e.target.value) || 0,
                          })
                        }
                        className="w-20"
                        placeholder="Hour"
                      />
                      <span>:</span>
                      <Input
                        type="number"
                        min={0}
                        max={59}
                        value={editValues.minute}
                        onChange={(e) =>
                          setEditValues({
                            ...editValues,
                            minute: parseInt(e.target.value) || 0,
                          })
                        }
                        className="w-20"
                        placeholder="Min"
                      />
                      <Select
                        value={editValues.day_of_week}
                        onChange={(e) =>
                          setEditValues({
                            ...editValues,
                            day_of_week: e.target.value,
                          })
                        }
                        className="h-10"
                      >
                        <option value="">Daily</option>
                        <option value="0">Monday</option>
                        <option value="1">Tuesday</option>
                        <option value="2">Wednesday</option>
                        <option value="3">Thursday</option>
                        <option value="4">Friday</option>
                        <option value="5">Saturday</option>
                        <option value="6">Sunday</option>
                      </Select>
                      <Button
                        size="sm"
                        onClick={() => saveEdit(schedule.task_type)}
                        disabled={updateMutation.isPending}
                      >
                        Save
                      </Button>
                      <Button
                        size="sm"
                        variant="ghost"
                        onClick={() => setEditing(null)}
                      >
                        Cancel
                      </Button>
                    </div>
                  ) : (
                    <div className="flex items-center gap-2 text-sm">
                      <Calendar className="h-4 w-4 text-muted-foreground" />
                      <span>{formatSchedule(schedule)}</span>
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => startEditing(schedule)}
                      >
                        Edit
                      </Button>
                    </div>
                  )}

                  <div className="text-xs text-muted-foreground space-y-1">
                    <p>
                      Last run:{' '}
                      {schedule.last_run_at
                        ? formatRelativeTime(schedule.last_run_at)
                        : 'Never'}
                    </p>
                    {schedule.enabled && schedule.next_run_at && (
                      <p>
                        Next run: {formatRelativeTime(schedule.next_run_at)}
                      </p>
                    )}
                    <p>Total runs: {schedule.run_count}</p>
                  </div>
                </div>

                <div className="flex flex-col gap-2">
                  {schedule.enabled ? (
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => disableMutation.mutate(schedule.task_type)}
                      disabled={disableMutation.isPending}
                    >
                      <X className="h-4 w-4 mr-2" />
                      Disable
                    </Button>
                  ) : (
                    <Button
                      size="sm"
                      onClick={() => enableMutation.mutate(schedule.task_type)}
                      disabled={enableMutation.isPending}
                    >
                      <Check className="h-4 w-4 mr-2" />
                      Enable
                    </Button>
                  )}
                  <Button
                    size="sm"
                    variant="secondary"
                    onClick={() => runNowMutation.mutate(schedule.task_type)}
                    disabled={runNowMutation.isPending}
                  >
                    <Play className="h-4 w-4 mr-2" />
                    Run Now
                  </Button>
                </div>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>

      {/* Info Card */}
      <Card className="bg-muted">
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-sm">
            <AlertCircle className="h-4 w-4" />
            About the Scheduler
          </CardTitle>
        </CardHeader>
        <CardContent className="text-sm text-muted-foreground space-y-2">
          <p>
            The scheduler reads configuration from the database every 60
            seconds. Changes are applied automatically, or you can click
            &quot;Apply Changes&quot; to force an immediate refresh.
          </p>
          <p>
            All schedules are disabled by default. Enable them to start
            automatic processing.
          </p>
        </CardContent>
      </Card>
    </div>
  )
}
