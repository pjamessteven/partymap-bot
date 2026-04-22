'use client'

import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  getSettings,
  updateSetting,
  getAutoProcessStatus,
  enableAutoProcess,
  disableAutoProcess,
} from '@/lib/api'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Check, X, Save, RotateCcw } from 'lucide-react'
import { GoabaseSyncPanel } from '@/components/GoabaseSyncPanel'
import type { SettingCategory } from '@/types'

const categoryLabels: Record<string, string> = {
  pipeline: 'Pipeline',
  scheduling: 'Scheduling',
  cost: 'Cost & Budget',
  general: 'General',
  goabase: 'Goabase Sync',
}

export default function SettingsPage() {
  const queryClient = useQueryClient()
  const [editing, setEditing] = useState<string | null>(null)
  const [editValue, setEditValue] = useState<unknown>(null)

  const { data: settings, isLoading } = useQuery({
    queryKey: ['settings'],
    queryFn: () => getSettings(),
  })

  const { data: autoProcess } = useQuery({
    queryKey: ['auto-process'],
    queryFn: getAutoProcessStatus,
  })

  const updateMutation = useMutation({
    mutationFn: ({ key, value }: { key: string; value: unknown }) =>
      updateSetting(key, value),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['settings'] })
      setEditing(null)
    },
  })

  const enableAutoMutation = useMutation({
    mutationFn: enableAutoProcess,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['auto-process'] })
      queryClient.invalidateQueries({ queryKey: ['settings'] })
    },
  })

  const disableAutoMutation = useMutation({
    mutationFn: disableAutoProcess,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['auto-process'] })
      queryClient.invalidateQueries({ queryKey: ['settings'] })
    },
  })

  const startEditing = (key: string, value: unknown) => {
    setEditing(key)
    setEditValue(value)
  }

  const saveEdit = (key: string) => {
    updateMutation.mutate({ key, value: editValue })
  }

  const renderValue = (setting: NonNullable<typeof settings>['settings'][number]) => {
    if (editing === setting.key) {
      switch (setting.value_type) {
        case 'boolean':
          return (
            <select
              value={editValue as string}
              onChange={(e) => setEditValue(e.target.value === 'true')}
              className="h-10 rounded-md border border-input bg-background px-3"
            >
              <option value="true">True</option>
              <option value="false">False</option>
            </select>
          )
        case 'integer':
        case 'float':
          return (
            <Input
              type="number"
              value={editValue as number}
              onChange={(e) =>
                setEditValue(
                  setting.value_type === 'integer'
                    ? parseInt(e.target.value)
                    : parseFloat(e.target.value)
                )
              }
              className="w-32"
            />
          )
        case 'json':
          return (
            <Input
              value={JSON.stringify(editValue)}
              onChange={(e) => {
                try {
                  setEditValue(JSON.parse(e.target.value))
                } catch {
                  setEditValue(e.target.value)
                }
              }}
              className="w-64 font-mono text-sm"
            />
          )
        default:
          return (
            <Input
              value={editValue as string}
              onChange={(e) => setEditValue(e.target.value)}
              className="w-64"
            />
          )
      }
    }

    switch (setting.value_type) {
      case 'boolean':
        return setting.value ? (
          <Check className="h-5 w-5 text-green-500" />
        ) : (
          <X className="h-5 w-5 text-red-500" />
        )
      case 'json':
        return (
          <code className="bg-muted px-2 py-1 rounded text-sm">
            {JSON.stringify(setting.value)}
          </code>
        )
      default:
        return <span>{String(setting.value)}</span>
    }
  }

  if (isLoading) {
    return (
      <div className="space-y-6">
        <h1 className="text-3xl font-bold">Settings</h1>
        <div className="text-center py-8">Loading...</div>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <h1 className="text-3xl font-bold">Settings</h1>

      {/* Auto-Process Toggle */}
      <Card className={autoProcess?.enabled ? 'border-green-500' : 'border-yellow-500'}>
        <CardHeader>
          <CardTitle className="flex items-center justify-between">
            <span>Auto-Process Mode</span>
            <Badge
              variant={autoProcess?.enabled ? 'default' : 'secondary'}
              className={autoProcess?.enabled ? 'bg-green-500 text-white' : ''}
            >
              {autoProcess?.enabled ? 'Enabled' : 'Disabled'}
            </Badge>
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <p className="text-sm text-muted-foreground">
            {autoProcess?.description}
          </p>
          <div className="flex gap-2">
            {autoProcess?.enabled ? (
              <Button
                variant="outline"
                onClick={() => disableAutoMutation.mutate()}
                disabled={disableAutoMutation.isPending}
              >
                <X className="h-4 w-4 mr-2" />
                Disable Auto-Process
              </Button>
            ) : (
              <Button
                onClick={() => enableAutoMutation.mutate()}
                disabled={enableAutoMutation.isPending}
              >
                <Check className="h-4 w-4 mr-2" />
                Enable Auto-Process
              </Button>
            )}
          </div>
        </CardContent>
      </Card>

      {/* Goabase Sync Panel */}
      <GoabaseSyncPanel />

      {/* Settings by Category */}
      {settings?.by_category &&
        Object.entries(settings.by_category).map(([category, categorySettings]) => (
          <Card key={category}>
            <CardHeader>
              <CardTitle>{categoryLabels[category as SettingCategory] || category}</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="space-y-4">
                {categorySettings.map((setting) => (
                  <div
                    key={setting.key}
                    className={`flex items-center justify-between py-2 border-b last:border-0 ${
                      setting.key === 'auto_research_on_discover' || 
                      setting.key === 'auto_sync_on_research_success' 
                        ? autoProcess?.enabled 
                          ? 'opacity-100' 
                          : 'opacity-50'
                        : ''
                    }`}
                  >
                    <div className="space-y-1">
                      <div className="font-medium flex items-center gap-2">
                        {setting.key}
                        {(setting.key === 'auto_research_on_discover' || 
                          setting.key === 'auto_sync_on_research_success') && (
                          <Badge variant="outline" className="text-xs">
                            Dependent
                          </Badge>
                        )}
                      </div>
                      {setting.description && (
                        <p className="text-sm text-muted-foreground">
                          {setting.description}
                        </p>
                      )}
                      {(setting.key === 'auto_research_on_discover' || 
                        setting.key === 'auto_sync_on_research_success') && 
                        !autoProcess?.enabled && (
                        <p className="text-xs text-yellow-600">
                          Requires auto_process to be enabled
                        </p>
                      )}
                      <Badge variant="outline" className="text-xs">
                        {setting.value_type}
                      </Badge>
                    </div>
                    <div className="flex items-center gap-2">
                      {renderValue(setting)}
                      {setting.editable &&
                        (editing === setting.key ? (
                          <Button
                            size="sm"
                            onClick={() => saveEdit(setting.key)}
                            disabled={updateMutation.isPending}
                          >
                            <Save className="h-4 w-4" />
                          </Button>
                        ) : (
                          <Button
                            size="sm"
                            variant="ghost"
                            onClick={() => startEditing(setting.key, setting.value)}
                            disabled={
                              (setting.key === 'auto_research_on_discover' || 
                               setting.key === 'auto_sync_on_research_success') && 
                              !autoProcess?.enabled
                            }
                          >
                            Edit
                          </Button>
                        ))}
                    </div>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>
        ))}
    </div>
  )
}
