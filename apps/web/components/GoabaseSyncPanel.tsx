'use client'

import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { 
  startGoabaseSync, 
  stopGoabaseSync, 
  getGoabaseSyncStatus, 
  getGoabaseSettings,
  updateGoabaseSettings 
} from '@/lib/api'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Progress } from '@/components/ui/progress'
import type { GoabaseSettings } from '@/types'
import { Play, Square, RefreshCw, Settings2 } from 'lucide-react'

export function GoabaseSyncPanel() {
  const queryClient = useQueryClient()
  const [showSettings, setShowSettings] = useState(false)

  // Queries
  const { data: syncStatus, isLoading: statusLoading } = useQuery({
    queryKey: ['goabase-status'],
    queryFn: getGoabaseSyncStatus,
    refetchInterval: 2000,
  })

  const { data: settings } = useQuery({
    queryKey: ['goabase-settings'],
    queryFn: getGoabaseSettings,
  })

  // Mutations
  const startMutation = useMutation({
    mutationFn: startGoabaseSync,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['goabase-status'] })
    },
  })

  const stopMutation = useMutation({
    mutationFn: stopGoabaseSync,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['goabase-status'] })
    },
  })

  const updateSettingsMutation = useMutation({
    mutationFn: updateGoabaseSettings,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['goabase-settings'] })
      setShowSettings(false)
    },
  })

  const isRunning = syncStatus?.is_running
  const progress = syncStatus?.progress_percentage || 0

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <CardTitle className="flex items-center gap-2">
            Goabase Sync
            <Badge variant={isRunning ? "default" : "secondary"}>
              {isRunning ? 'Running' : 'Idle'}
            </Badge>
          </CardTitle>
          <div className="flex gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={() => setShowSettings(!showSettings)}
            >
              <Settings2 className="h-4 w-4 mr-1" />
              Settings
            </Button>
            {isRunning ? (
              <Button
                variant="destructive"
                size="sm"
                onClick={() => stopMutation.mutate()}
                disabled={stopMutation.isPending}
              >
                <Square className="h-4 w-4 mr-1" />
                Stop
              </Button>
            ) : (
              <Button
                variant="default"
                size="sm"
                onClick={() => startMutation.mutate()}
                disabled={startMutation.isPending}
              >
                <Play className="h-4 w-4 mr-1" />
                Start Sync
              </Button>
            )}
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Status */}
        {statusLoading ? (
          <div className="text-sm text-muted-foreground">Loading status...</div>
        ) : (
          <>
            {/* Progress */}
            {isRunning && (
              <div className="space-y-2">
                <div className="flex justify-between text-sm">
                  <span>Progress</span>
                  <span>{progress}%</span>
                </div>
                <Progress value={progress} />
                {syncStatus?.current_operation && (
                  <p className="text-sm text-muted-foreground">
                    {syncStatus.current_operation}
                  </p>
                )}
              </div>
            )}

            {/* Results */}
                {syncStatus?.completed_at && !isRunning && (
                  <div className="grid grid-cols-4 gap-4 text-center">
                    <div className="space-y-1">
                      <div className="text-2xl font-bold text-green-600">
                        {syncStatus.new_count}
                      </div>
                      <div className="text-xs text-muted-foreground">New</div>
                    </div>
                    <div className="space-y-1">
                      <div className="text-2xl font-bold text-blue-600">
                        {syncStatus.update_count}
                      </div>
                      <div className="text-xs text-muted-foreground">Updates</div>
                    </div>
                    <div className="space-y-1">
                      <div className="text-2xl font-bold text-gray-600">
                        {syncStatus.unchanged_count}
                      </div>
                      <div className="text-xs text-muted-foreground">Unchanged</div>
                    </div>
                    <div className="space-y-1">
                      <div className="text-2xl font-bold text-red-600">
                        {syncStatus.error_count}
                      </div>
                      <div className="text-xs text-muted-foreground">Errors</div>
                    </div>
                  </div>
                )}

                {/* Last run */}
                {syncStatus?.completed_at && (
                  <p className="text-sm text-muted-foreground">
                    Last completed: {new Date(syncStatus.completed_at).toLocaleString()}
                  </p>
                )}
          </>
        )}

        {/* Settings Panel */}
        {showSettings && settings && (
          <div className="border-t pt-4 space-y-4">
            <h4 className="font-medium">Sync Settings</h4>
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <label className="text-sm">Enabled</label>
                <select
                  className="w-full border rounded px-2 py-1"
                  value={settings.goabase_sync_enabled.toString()}
                  onChange={(e) =>
                    updateSettingsMutation.mutate({
                      goabase_sync_enabled: e.target.value === 'true',
                    })
                  }
                >
                  <option value="true">Yes</option>
                  <option value="false">No</option>
                </select>
              </div>
              <div className="space-y-2">
                <label className="text-sm">Frequency</label>
                <select
                  className="w-full border rounded px-2 py-1"
                  value={settings.goabase_sync_frequency}
                  onChange={(e) =>
                    updateSettingsMutation.mutate({
                      goabase_sync_frequency: e.target.value as GoabaseSettings['goabase_sync_frequency'],
                    })
                  }
                >
                  <option value="daily">Daily</option>
                  <option value="weekly">Weekly</option>
                  <option value="monthly">Monthly</option>
                </select>
              </div>
              <div className="space-y-2">
                <label className="text-sm">Day (if weekly)</label>
                <select
                  className="w-full border rounded px-2 py-1"
                  value={settings.goabase_sync_day}
                  onChange={(e) =>
                    updateSettingsMutation.mutate({
                      goabase_sync_day: e.target.value as GoabaseSettings['goabase_sync_day'],
                    })
                  }
                >
                  <option value="monday">Monday</option>
                  <option value="tuesday">Tuesday</option>
                  <option value="wednesday">Wednesday</option>
                  <option value="thursday">Thursday</option>
                  <option value="friday">Friday</option>
                  <option value="saturday">Saturday</option>
                  <option value="sunday">Sunday</option>
                </select>
              </div>
              <div className="space-y-2">
                <label className="text-sm">Hour (0-23)</label>
                <input
                  type="number"
                  min={0}
                  max={23}
                  className="w-full border rounded px-2 py-1"
                  value={settings.goabase_sync_hour}
                  onChange={(e) =>
                    updateSettingsMutation.mutate({
                      goabase_sync_hour: parseInt(e.target.value),
                    })
                  }
                />
              </div>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  )
}
