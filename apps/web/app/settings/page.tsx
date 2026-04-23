'use client'

import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  getSettings,
  updateSetting,
  getAutoProcessStatus,
  enableAutoProcess,
  disableAutoProcess,
  getSchedules,
  updateSchedule,
  enableSchedule,
  disableSchedule,
  runTaskNow,
  applyScheduleChanges,
} from '@/lib/api'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Switch } from '@/components/ui/switch'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { Select } from '@/components/ui/select'
import { Separator } from '@/components/ui/separator'
import { useToast } from '@/components/ui/toast-provider'
import { SkeletonCard } from '@/components/ui/skeleton'
import {
  Check,
  X,
  Play,
  RefreshCw,
  Clock,
  Calendar,
  Settings2,
  Zap,
  DollarSign,
  AlertCircle,
  ChevronRight,
  Bot,
  Search,
  Brain,
  UploadCloud,
  Loader2,
  Save,
} from 'lucide-react'
import { formatRelativeTime, cn } from '@/lib/utils'
import type { ScheduleConfig, SystemSettingResponse } from '@/types'

// Task descriptions for schedules
const taskDescriptions: Record<string, string> = {
  discovery: 'Discovers new festivals using Exa search and Goabase API',
  goabase_sync: 'Synchronizes events from Goabase psychedelic festival database',
  cleanup_failed: 'Removes festivals stuck in failed state for 30+ days',
}

const taskIcons: Record<string, React.ReactNode> = {
  discovery: <Search className="h-5 w-5" />,
  goabase_sync: <Bot className="h-5 w-5" />,
  cleanup_failed: <RefreshCw className="h-5 w-5" />,
}

const daysOfWeek = [
  { value: '', label: 'Daily' },
  { value: '0', label: 'Monday' },
  { value: '1', label: 'Tuesday' },
  { value: '2', label: 'Wednesday' },
  { value: '3', label: 'Thursday' },
  { value: '4', label: 'Friday' },
  { value: '5', label: 'Saturday' },
  { value: '6', label: 'Sunday' },
]

// Generate hours 00-23
const hours = Array.from({ length: 24 }, (_, i) => ({
  value: i.toString(),
  label: i.toString().padStart(2, '0'),
}))

// Generate minutes 00-59
const minutes = Array.from({ length: 60 }, (_, i) => ({
  value: i.toString(),
  label: i.toString().padStart(2, '0'),
}))

export default function SettingsPage() {
  const queryClient = useQueryClient()
  const { success, error: showError } = useToast()
  const [editingSchedule, setEditingSchedule] = useState<string | null>(null)
  const [editScheduleValues, setEditScheduleValues] = useState({
    hour: 0,
    minute: 0,
    day_of_week: '',
  })

  // Fetch all data
  const { data: settings, isLoading: settingsLoading } = useQuery({
    queryKey: ['settings'],
    queryFn: () => getSettings(),
  })

  const { data: autoProcess, isLoading: autoProcessLoading } = useQuery({
    queryKey: ['auto-process'],
    queryFn: getAutoProcessStatus,
  })

  const { data: schedules, isLoading: schedulesLoading } = useQuery({
    queryKey: ['schedules'],
    queryFn: getSchedules,
  })

  // Mutations
  const updateSettingMutation = useMutation({
    mutationFn: ({ key, value }: { key: string; value: unknown }) => updateSetting(key, value),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['settings'] })
      success('Setting saved')
    },
    onError: (err: Error) => showError(err.message || 'Failed to save setting'),
  })

  const enableAutoMutation = useMutation({
    mutationFn: enableAutoProcess,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['auto-process'] })
      queryClient.invalidateQueries({ queryKey: ['settings'] })
      success('Auto-process enabled. Festivals will now flow through the pipeline automatically.')
    },
    onError: (err: Error) => showError(err.message || 'Failed to enable auto-process'),
  })

  const disableAutoMutation = useMutation({
    mutationFn: disableAutoProcess,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['auto-process'] })
      queryClient.invalidateQueries({ queryKey: ['settings'] })
      success('Auto-process disabled. Manual mode activated.')
    },
    onError: (err: Error) => showError(err.message || 'Failed to disable auto-process'),
  })

  const enableScheduleMutation = useMutation({
    mutationFn: enableSchedule,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['schedules'] })
      success('Schedule enabled')
    },
    onError: (err: Error) => showError(err.message || 'Failed to enable schedule'),
  })

  const disableScheduleMutation = useMutation({
    mutationFn: disableSchedule,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['schedules'] })
      success('Schedule disabled')
    },
    onError: (err: Error) => showError(err.message || 'Failed to disable schedule'),
  })

  const updateScheduleMutation = useMutation({
    mutationFn: ({ taskType, updates }: { taskType: string; updates: { hour: number; minute: number; day_of_week?: number } }) =>
      updateSchedule(taskType, updates),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['schedules'] })
      setEditingSchedule(null)
      success('Schedule updated')
    },
    onError: (err: Error) => showError(err.message || 'Failed to update schedule'),
  })

  const runNowMutation = useMutation({
    mutationFn: runTaskNow,
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['schedules'] })
      success(`Task "${data.task_type}" started successfully`)
    },
    onError: (err: Error) => showError(err.message || 'Failed to run task'),
  })

  const applyMutation = useMutation({
    mutationFn: applyScheduleChanges,
    onSuccess: () => {
      success('Schedule changes applied')
    },
    onError: (err: Error) => showError(err.message || 'Failed to apply changes'),
  })

  const startEditingSchedule = (schedule: ScheduleConfig) => {
    setEditingSchedule(schedule.task_type)
    setEditScheduleValues({
      hour: schedule.hour,
      minute: schedule.minute,
      day_of_week: schedule.day_of_week?.toString() ?? '',
    })
  }

  const saveScheduleEdit = (taskType: string) => {
    updateScheduleMutation.mutate({
      taskType,
      updates: {
        hour: editScheduleValues.hour,
        minute: editScheduleValues.minute,
        day_of_week: editScheduleValues.day_of_week
          ? parseInt(editScheduleValues.day_of_week)
          : undefined,
      },
    })
  }

  const formatScheduleTime = (schedule: ScheduleConfig) => {
    const time = `${schedule.hour.toString().padStart(2, '0')}:${schedule.minute.toString().padStart(2, '0')}`
    const dow = schedule.day_of_week
    if (dow !== null && dow !== undefined) {
      const day = daysOfWeek.find((d) => d.value === dow.toString())
      return `${day?.label} at ${time} UTC`
    }
    return `Daily at ${time} UTC`
  }

  const isLoading = settingsLoading || autoProcessLoading || schedulesLoading

  if (isLoading) {
    return (
      <div className="space-y-6">
        <div>
          <h1 className="text-2xl sm:text-3xl font-bold">Settings</h1>
          <p className="text-muted-foreground mt-2">Manage your pipeline configuration</p>
        </div>
        <SkeletonCard className="h-64" />
        <SkeletonCard className="h-96" />
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl sm:text-3xl font-bold">Settings</h1>
        <p className="text-muted-foreground mt-2 text-lg">
          Configure your festival discovery pipeline
        </p>
      </div>

      {/* Pipeline Mode Card */}
      <Card
        className={
          autoProcess?.enabled
            ? 'border-green-500/50 shadow-lg shadow-green-500/10'
            : 'border-yellow-500/50 shadow-lg shadow-yellow-500/10'
        }
      >
        <CardHeader className="pb-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div
                className={`p-2 rounded-lg ${
                  autoProcess?.enabled
                    ? 'bg-green-500/10 text-green-500'
                    : 'bg-yellow-500/10 text-yellow-500'
                }`}
              >
                <Zap className="h-6 w-6" />
              </div>
              <div>
                <CardTitle className="text-2xl">Pipeline Mode</CardTitle>
                <CardDescription className="text-base mt-1">
                  Control how festivals flow through the system
                </CardDescription>
              </div>
            </div>
            <Badge
              variant={autoProcess?.enabled ? 'default' : 'secondary'}
              className={`text-sm px-4 py-1.5 ${
                autoProcess?.enabled ? 'bg-green-500 hover:bg-green-600' : ''
              }`}
            >
              {autoProcess?.enabled ? (
                <>
                  <Check className="h-4 w-4 mr-1.5" /> Auto Mode
                </>
              ) : (
                <>
                  <Settings2 className="h-4 w-4 mr-1.5" /> Manual Mode
                </>
              )}
            </Badge>
          </div>
        </CardHeader>
        <CardContent className="space-y-6">
          {/* Mode Toggle */}
          <div className="flex items-center justify-between p-4 rounded-xl bg-muted/50">
            <div className="space-y-1">
              <Label className="text-base font-semibold">
                {autoProcess?.enabled ? 'Automatic Processing' : 'Manual Processing'}
              </Label>
              <p className="text-sm text-muted-foreground">
                {autoProcess?.enabled
                  ? 'Festivals automatically progress through all pipeline stages'
                  : 'Each stage requires manual approval and triggering'}
              </p>
            </div>
            <Switch
              checked={autoProcess?.enabled ?? false}
              onCheckedChange={(checked) => {
                if (checked) enableAutoMutation.mutate()
                else disableAutoMutation.mutate()
              }}
              disabled={enableAutoMutation.isPending || disableAutoMutation.isPending}
              className="data-[state=checked]:bg-green-500"
            />
          </div>

          {/* Visual Pipeline Flow */}
          <div className="p-6 rounded-xl bg-muted/30">
            <p className="text-sm font-medium text-muted-foreground mb-4">Pipeline Flow</p>
            <div className="flex items-center justify-center gap-2 flex-wrap">
              <div
                className={`flex flex-col items-center gap-2 p-4 rounded-xl min-w-[120px] transition-colors ${
                  autoProcess?.enabled ? 'bg-green-500/10 text-green-600' : 'bg-muted'
                }`}
              >
                <Search className="h-6 w-6" />
                <span className="text-sm font-medium">Discovery</span>
                <span className="text-xs text-muted-foreground">Find festivals</span>
              </div>

              <ChevronRight className="h-5 w-5 text-muted-foreground" />

              <div
                className={`flex flex-col items-center gap-2 p-4 rounded-xl min-w-[120px] transition-colors ${
                  autoProcess?.enabled ? 'bg-green-500/10 text-green-600' : 'bg-muted'
                }`}
              >
                <Brain className="h-6 w-6" />
                <span className="text-sm font-medium">Research</span>
                <span className="text-xs text-muted-foreground">Extract details</span>
              </div>

              <ChevronRight className="h-5 w-5 text-muted-foreground" />

              <div
                className={`flex flex-col items-center gap-2 p-4 rounded-xl min-w-[120px] transition-colors ${
                  autoProcess?.enabled ? 'bg-green-500/10 text-green-600' : 'bg-muted'
                }`}
              >
                <UploadCloud className="h-6 w-6" />
                <span className="text-sm font-medium">Sync</span>
                <span className="text-xs text-muted-foreground">Push to PartyMap</span>
              </div>
            </div>
          </div>

          {/* Mode Description */}
          <div className="rounded-lg bg-muted/50 p-4">
            <p className="text-sm text-muted-foreground leading-relaxed">
              {autoProcess?.enabled
                ? 'In Auto Mode, festivals discovered by the discovery agent will automatically run through deduplication, research, and sync to PartyMap. Perfect for production use.'
                : 'In Manual Mode, festivals stay in their current state after each stage. You must manually trigger deduplication, research, and sync. Useful for testing and debugging individual pipeline stages.'}
            </p>
          </div>
        </CardContent>
      </Card>

      {/* Schedule Management Card */}
      <Card>
        <CardHeader className="pb-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="p-2 rounded-lg bg-blue-500/10 text-blue-500">
                <Calendar className="h-6 w-6" />
              </div>
              <div>
                <CardTitle className="text-2xl">Schedule Management</CardTitle>
                <CardDescription className="text-base mt-1">
                  Configure when automated tasks run
                </CardDescription>
              </div>
            </div>
            <Button
              variant="outline"
              size="sm"
              onClick={() => applyMutation.mutate()}
              disabled={applyMutation.isPending}
            >
              <RefreshCw
                className={`h-4 w-4 mr-2 ${applyMutation.isPending ? 'animate-spin' : ''}`}
              />
              Apply Changes
            </Button>
          </div>
        </CardHeader>
        <CardContent>
          <div className="space-y-6">
            {schedules?.map((schedule) => (
              <div
                key={schedule.task_type}
                className="p-6 rounded-xl border bg-card hover:bg-muted/30 transition-colors"
              >
                <div className="flex items-start justify-between gap-4">
                  <div className="flex-1 space-y-4">
                    {/* Header Row */}
                    <div className="flex items-center gap-3">
                      <div className="p-2 rounded-lg bg-muted">
                        {taskIcons[schedule.task_type] || <Clock className="h-5 w-5" />}
                      </div>
                      <div>
                        <h3 className="text-lg font-semibold capitalize">
                          {schedule.task_type.replace(/_/g, ' ')}
                        </h3>
                        <p className="text-sm text-muted-foreground">
                          {taskDescriptions[schedule.task_type] || 'Scheduled task'}
                        </p>
                      </div>
                    </div>

                    {/* Schedule Configuration */}
                    {editingSchedule === schedule.task_type ? (
                      <div className="flex flex-wrap items-center gap-3 p-4 rounded-lg bg-muted">
                        <Clock className="h-4 w-4 text-muted-foreground" />

                        <Select
                          value={editScheduleValues.hour.toString()}
                          onChange={(e) =>
                            setEditScheduleValues({
                              ...editScheduleValues,
                              hour: parseInt(e.target.value),
                            })
                          }
                          className="w-20"
                        >
                          {hours.map((h) => (
                            <option key={h.value} value={h.value}>
                              {h.label}
                            </option>
                          ))}
                        </Select>

                        <span className="text-muted-foreground">:</span>

                        <Select
                          value={editScheduleValues.minute.toString()}
                          onChange={(e) =>
                            setEditScheduleValues({
                              ...editScheduleValues,
                              minute: parseInt(e.target.value),
                            })
                          }
                          className="w-20"
                        >
                          {minutes.map((m) => (
                            <option key={m.value} value={m.value}>
                              {m.label}
                            </option>
                          ))}
                        </Select>

                        <Select
                          value={editScheduleValues.day_of_week}
                          onChange={(e) =>
                            setEditScheduleValues({
                              ...editScheduleValues,
                              day_of_week: e.target.value,
                            })
                          }
                          className="w-32"
                        >
                          {daysOfWeek.map((day) => (
                            <option key={day.value} value={day.value}>
                              {day.label}
                            </option>
                          ))}
                        </Select>

                        <div className="flex items-center gap-2 ml-auto">
                          <Button
                            size="sm"
                            onClick={() => saveScheduleEdit(schedule.task_type)}
                            disabled={updateScheduleMutation.isPending}
                          >
                            Save
                          </Button>
                          <Button
                            size="sm"
                            variant="ghost"
                            onClick={() => setEditingSchedule(null)}
                          >
                            Cancel
                          </Button>
                        </div>
                      </div>
                    ) : (
                      <div className="flex items-center gap-4">
                        <div className="flex items-center gap-2 text-sm">
                          <Clock className="h-4 w-4 text-muted-foreground" />
                          <span className="font-medium">
                            {formatScheduleTime(schedule)}
                          </span>
                        </div>
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => startEditingSchedule(schedule)}
                        >
                          Edit Time
                        </Button>
                      </div>
                    )}

                    {/* Schedule Stats */}
                    <div className="flex flex-wrap items-center gap-4 text-xs text-muted-foreground">
                      <span>
                        Last run:{' '}
                        {schedule.last_run_at
                          ? formatRelativeTime(schedule.last_run_at)
                          : 'Never'}
                      </span>
                      {schedule.enabled && schedule.next_run_at && (
                        <>
                          <Separator orientation="vertical" className="h-3" />
                          <span>
                            Next run: {formatRelativeTime(schedule.next_run_at)}
                          </span>
                        </>
                      )}
                      <Separator orientation="vertical" className="h-3" />
                      <span>Total runs: {schedule.run_count}</span>
                    </div>
                  </div>

                  {/* Actions */}
                  <div className="flex flex-col items-end gap-3">
                    <div className="flex items-center gap-3">
                      <span className="text-sm text-muted-foreground">
                        {schedule.enabled ? 'Enabled' : 'Disabled'}
                      </span>
                      <Switch
                        checked={schedule.enabled}
                        onCheckedChange={(checked) => {
                          if (checked)
                            enableScheduleMutation.mutate(schedule.task_type)
                          else
                            disableScheduleMutation.mutate(schedule.task_type)
                        }}
                        disabled={
                          enableScheduleMutation.isPending ||
                          disableScheduleMutation.isPending
                        }
                      />
                    </div>
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
              </div>
            ))}
          </div>

          {/* Schedule Info */}
          <div className="mt-6 p-4 rounded-lg bg-muted/50 flex items-start gap-3">
            <AlertCircle className="h-5 w-5 text-muted-foreground flex-shrink-0 mt-0.5" />
            <div className="text-sm text-muted-foreground space-y-1">
              <p>
                The scheduler checks for updates every 60 seconds. All schedules
                are disabled by default.
              </p>
              <p>
                Click &quot;Apply Changes&quot; to force an immediate refresh of the
                scheduler configuration.
              </p>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Settings by Category */}
      {settings?.by_category &&
        Object.entries(settings.by_category)
          .filter(([category]) => category !== 'scheduling')
          .map(([category, categorySettings]) => (
            <SettingsCategoryCard
              key={category}
              category={category}
              settings={categorySettings}
              onUpdate={updateSettingMutation.mutate}
              isPending={updateSettingMutation.isPending}
            />
          ))}
    </div>
  )
}

function SettingsCategoryCard({
  category,
  settings,
  onUpdate,
  isPending,
}: {
  category: string
  settings: SystemSettingResponse[]
  onUpdate: (payload: { key: string; value: unknown }) => void
  isPending: boolean
}) {
  const categoryIcons: Record<string, React.ReactNode> = {
    cost: <DollarSign className="h-6 w-6" />,
    pipeline: <Zap className="h-6 w-6" />,
    goabase: <Bot className="h-6 w-6" />,
    general: <Settings2 className="h-6 w-6" />,
  }

  const categoryColors: Record<string, string> = {
    cost: 'bg-amber-500/10 text-amber-500',
    pipeline: 'bg-purple-500/10 text-purple-500',
    goabase: 'bg-pink-500/10 text-pink-500',
    general: 'bg-gray-500/10 text-gray-500',
  }

  return (
    <Card>
      <CardHeader className="pb-4">
        <div className="flex items-center gap-3">
          <div
            className={`p-2 rounded-lg ${
              categoryColors[category] || categoryColors.general
            }`}
          >
            {categoryIcons[category] || categoryIcons.general}
          </div>
          <div>
            <CardTitle className="text-xl capitalize">
              {category} Settings
            </CardTitle>
            <CardDescription>
              {settings.length} setting{settings.length !== 1 ? 's' : ''}
            </CardDescription>
          </div>
        </div>
      </CardHeader>
      <CardContent>
        <div className="space-y-4">
          {settings.map((setting) => (
            <SettingEditor
              key={setting.key}
              setting={setting}
              onUpdate={onUpdate}
              isPending={isPending}
            />
          ))}
        </div>
      </CardContent>
    </Card>
  )
}

function SettingEditor({
  setting,
  onUpdate,
  isPending,
}: {
  setting: SystemSettingResponse
  onUpdate: (payload: { key: string; value: unknown }) => void
  isPending: boolean
}) {
  const [editValue, setEditValue] = useState<unknown>(setting.value)
  const [isEditing, setIsEditing] = useState(false)

  const handleSave = () => {
    let parsedValue: unknown = editValue

    if (setting.value_type === 'integer') {
      parsedValue = parseInt(String(editValue), 10)
      if (isNaN(parsedValue as number)) {
        parsedValue = 0
      }
    } else if (setting.value_type === 'float') {
      parsedValue = parseFloat(String(editValue))
      if (isNaN(parsedValue as number)) {
        parsedValue = 0
      }
    } else if (setting.value_type === 'boolean') {
      parsedValue = Boolean(editValue)
    } else if (setting.value_type === 'json') {
      try {
        parsedValue =
          typeof editValue === 'string' ? JSON.parse(editValue) : editValue
      } catch {
        // Invalid JSON, keep as string
        parsedValue = editValue
      }
    }

    onUpdate({ key: setting.key, value: parsedValue })
    setIsEditing(false)
  }

  const handleCancel = () => {
    setEditValue(setting.value)
    setIsEditing(false)
  }

  const toggleBoolean = (checked: boolean) => {
    onUpdate({ key: setting.key, value: checked })
  }

  return (
    <div className="flex items-start justify-between p-4 rounded-lg border gap-4">
      <div className="space-y-1 flex-1 min-w-0">
        <Label className="text-base font-medium break-words">
          {setting.key}
        </Label>
        {setting.description && (
          <p className="text-sm text-muted-foreground">{setting.description}</p>
        )}
      </div>

      <div className="flex items-center gap-3 flex-shrink-0">
        {setting.value_type === 'boolean' ? (
          <Switch
            checked={Boolean(setting.value)}
            onCheckedChange={toggleBoolean}
            disabled={!setting.editable || isPending}
          />
        ) : isEditing ? (
          <div className="flex items-center gap-2">
            {setting.value_type === 'json' ? (
              <Textarea
                value={
                  typeof editValue === 'object'
                    ? JSON.stringify(editValue, null, 2)
                    : String(editValue)
                }
                onChange={(e) => setEditValue(e.target.value)}
                className="min-w-[200px] font-mono text-sm"
                rows={3}
              />
            ) : setting.value_type === 'integer' ? (
              <Input
                type="number"
                value={String(editValue)}
                onChange={(e) => setEditValue(e.target.value)}
                className="w-32"
              />
            ) : setting.value_type === 'float' ? (
              <Input
                type="number"
                step="0.01"
                value={String(editValue)}
                onChange={(e) => setEditValue(e.target.value)}
                className="w-32"
              />
            ) : (
              <Input
                type="text"
                value={String(editValue)}
                onChange={(e) => setEditValue(e.target.value)}
                className="min-w-[200px]"
              />
            )}
            <Button size="sm" onClick={handleSave} disabled={isPending}>
              {isPending ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Save className="h-4 w-4" />
              )}
            </Button>
            <Button size="sm" variant="ghost" onClick={handleCancel}>
              <X className="h-4 w-4" />
            </Button>
          </div>
        ) : (
          <div className="flex items-center gap-3">
            <code className="bg-muted px-3 py-1.5 rounded text-sm max-w-[200px] truncate">
              {setting.value_type === 'json'
                ? JSON.stringify(setting.value)
                : String(setting.value)}
            </code>
            {setting.editable && (
              <Button
                size="sm"
                variant="ghost"
                onClick={() => setIsEditing(true)}
              >
                Edit
              </Button>
            )}
          </div>
        )}
        <Badge variant="outline">{setting.value_type}</Badge>
      </div>
    </div>
  )
}
