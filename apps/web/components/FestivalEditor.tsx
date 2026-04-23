'use client'

import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { updateFestival } from '@/lib/api'
import { FestivalEditForm } from './FestivalEditForm'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { useToast } from '@/components/ui/toast-provider'
import { Loader2, Edit, AlertTriangle, CheckCircle } from 'lucide-react'

interface FestivalEditorProps {
  festivalId: string
  festivalName: string
  initialData?: Record<string, any>
  currentState: string
  open: boolean
  onOpenChange: (open: boolean) => void
}

export function FestivalEditor({
  festivalId,
  festivalName,
  initialData = {},
  currentState,
  open,
  onOpenChange,
}: FestivalEditorProps) {
  const [editedData, setEditedData] = useState<Record<string, any>>(initialData)
  const [promoteToResearched, setPromoteToResearched] = useState(
    currentState === 'researched_partial'
  )
  const { success, error: toastError } = useToast()
  const queryClient = useQueryClient()

  const updateMutation = useMutation({
    mutationFn: () =>
      updateFestival(festivalId, {
        research_data: editedData,
        promote_to_researched: promoteToResearched,
        reason: 'Manual edit via Festival Editor',
      }),
    onSuccess: (result) => {
      success(
        `Festival updated successfully${
          result.new_state !== result.previous_state
            ? ` and promoted to ${result.new_state}`
            : ''
        }`
      )
      queryClient.invalidateQueries({ queryKey: ['festival', festivalId] })
      queryClient.invalidateQueries({ queryKey: ['festivals'] })
      queryClient.invalidateQueries({ queryKey: ['stats'] })
      onOpenChange(false)
    },
    onError: (err: Error) => {
      toastError(err.message || 'Failed to update festival')
    },
  })

  const handleSave = () => {
    // Validate required fields
    if (!editedData.name?.trim()) {
      toastError('Festival name is required')
      return
    }
    if (!editedData.logo_url && promoteToResearched) {
      toastError('Logo is required to promote to RESEARCHED state')
      return
    }
    if (!editedData.event_dates?.length || !editedData.event_dates[0]?.start) {
      toastError('At least one event date with start date is required')
      return
    }

    updateMutation.mutate()
  }

  const isPartial = currentState === 'researched_partial'
  const hasLogo = Boolean(editedData.logo_url)
  const canPromote = isPartial && hasLogo

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-4xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Edit className="h-5 w-5" />
            Edit Festival: {festivalName}
          </DialogTitle>
          <DialogDescription>
            Manually edit the festival data before syncing to PartyMap.
            {isPartial && (
              <span className="block mt-1 text-amber-600">
                This festival is RESEARCHED_PARTIAL (missing logo). Add a logo to complete research.
              </span>
            )}
          </DialogDescription>
        </DialogHeader>

        {isPartial && (
          <Alert variant={hasLogo ? 'default' : 'destructive'}>
            <AlertTriangle className="h-4 w-4" />
            <AlertDescription>
              {hasLogo ? (
                <span className="flex items-center gap-2">
                  <CheckCircle className="h-4 w-4 text-green-500" />
                  Logo added! You can now promote this festival to RESEARCHED state.
                </span>
              ) : (
                'Logo is missing. Upload a logo image to complete the research and enable syncing.'
              )}
            </AlertDescription>
          </Alert>
        )}

        <div className="py-4">
          <FestivalEditForm
            initialData={initialData}
            onChange={setEditedData}
          />
        </div>

        {isPartial && (
          <div className="flex items-center gap-3 p-3 bg-muted rounded-lg">
            <input
              type="checkbox"
              id="promote"
              checked={promoteToResearched}
              onChange={(e) => setPromoteToResearched(e.target.checked)}
              disabled={!canPromote}
              className="h-4 w-4"
            />
            <label htmlFor="promote" className="text-sm cursor-pointer flex-1">
              <span className="font-medium">Promote to RESEARCHED state</span>
              <span className="text-muted-foreground block">
                {canPromote
                  ? 'Festival will be ready for sync after saving'
                  : 'Add a logo first to enable promotion'}
              </span>
            </label>
          </div>
        )}

        <DialogFooter className="gap-2">
          <Button
            variant="outline"
            onClick={() => onOpenChange(false)}
            disabled={updateMutation.isPending}
          >
            Cancel
          </Button>
          <Button
            onClick={handleSave}
            disabled={updateMutation.isPending}
            className="gap-2"
          >
            {updateMutation.isPending ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin" />
                Saving...
              </>
            ) : (
              <>
                <Edit className="h-4 w-4" />
                Save Changes
              </>
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
