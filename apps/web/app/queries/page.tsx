'use client'

import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  getQueries,
  createQuery,
  updateQuery,
  deleteQuery,
  enableQuery,
  disableQuery,
} from '@/lib/api'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Select } from '@/components/ui/select'
import { Check, X, Plus, Trash2, Edit2, Save } from 'lucide-react'
import { ConfirmDialog } from '@/components/ui/dialog-confirm'

export default function QueriesPage() {
  const queryClient = useQueryClient()
  const [newQuery, setNewQuery] = useState('')
  const [newCategory, setNewCategory] = useState('general')
  const [editing, setEditing] = useState<string | null>(null)
  const [editValues, setEditValues] = useState({ query_text: '', category: '' })
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false)
  const [queryToDelete, setQueryToDelete] = useState<string | null>(null)

  const { data: queries, isLoading } = useQuery({
    queryKey: ['queries'],
    queryFn: () => getQueries(),
  })

  const createMutation = useMutation({
    mutationFn: () => createQuery(newQuery, newCategory),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['queries'] })
      setNewQuery('')
    },
  })

  const updateMutation = useMutation({
    mutationFn: ({ id, updates }: { id: string; updates: Parameters<typeof updateQuery>[1] }) =>
      updateQuery(id, updates),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['queries'] })
      setEditing(null)
    },
  })

  const deleteMutation = useMutation({
    mutationFn: deleteQuery,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['queries'] }),
  })

  const enableMutation = useMutation({
    mutationFn: enableQuery,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['queries'] }),
  })

  const disableMutation = useMutation({
    mutationFn: disableQuery,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['queries'] }),
  })

  const startEditing = (query: NonNullable<typeof queries>[number]) => {
    setEditing(query.id)
    setEditValues({ query_text: query.query_text, category: query.category })
  }

  const saveEdit = (id: string) => {
    updateMutation.mutate({
      id,
      updates: {
        query_text: editValues.query_text,
        category: editValues.category,
      },
    })
  }

  const groupedQueries = queries?.reduce((acc, query) => {
    if (!acc[query.category]) acc[query.category] = []
    acc[query.category].push(query)
    return acc
  }, {} as Record<string, NonNullable<typeof queries>>)

  if (isLoading) {
    return (
      <div className="space-y-6">
        <h1 className="text-3xl font-bold">Discovery Queries</h1>
        <div className="text-center py-8">Loading...</div>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <h1 className="text-3xl font-bold">Discovery Queries</h1>

      {/* Add New Query */}
      <Card>
        <CardHeader>
          <CardTitle>Add New Query</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex gap-4">
            <Input
              placeholder="Query text (e.g., 'electronic music festivals in Berlin')"
              value={newQuery}
              onChange={(e) => setNewQuery(e.target.value)}
              className="flex-1"
            />
            <Select
              value={newCategory}
              onChange={(e) => setNewCategory(e.target.value)}
              className="h-10 w-40"
            >
              <option value="general">General</option>
              <option value="country">Country</option>
              <option value="city">City</option>
              <option value="genre">Genre</option>
            </Select>
            <Button
              onClick={() => createMutation.mutate()}
              disabled={!newQuery.trim() || createMutation.isPending}
            >
              <Plus className="h-4 w-4 mr-2" />
              Add Query
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* Query Groups */}
      <div className="space-y-6">
        {groupedQueries &&
          Object.entries(groupedQueries).map(([category, categoryQueries]) => (
            <Card key={category}>
              <CardHeader>
                <CardTitle className="capitalize">
                  {category} ({categoryQueries.length})
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="space-y-2">
                  {categoryQueries.map((query) => (
                    <div
                      key={query.id}
                      className="flex items-center justify-between rounded-lg border p-3"
                    >
                      {editing === query.id ? (
                        <>
                          <div className="flex gap-2 flex-1">
                            <Input
                              value={editValues.query_text}
                              onChange={(e) =>
                                setEditValues({
                                  ...editValues,
                                  query_text: e.target.value,
                                })
                              }
                              className="flex-1"
                            />
                            <Select
                              value={editValues.category}
                              onChange={(e) =>
                                setEditValues({
                                  ...editValues,
                                  category: e.target.value,
                                })
                              }
                              className="h-10 w-40"
                            >
                              <option value="general">General</option>
                              <option value="country">Country</option>
                              <option value="city">City</option>
                              <option value="genre">Genre</option>
                            </Select>
                          </div>
                          <div className="flex gap-2 ml-2">
                            <Button
                              size="sm"
                              onClick={() => saveEdit(query.id)}
                              disabled={updateMutation.isPending}
                            >
                              <Save className="h-4 w-4" />
                            </Button>
                            <Button
                              size="sm"
                              variant="ghost"
                              onClick={() => setEditing(null)}
                            >
                              <X className="h-4 w-4" />
                            </Button>
                          </div>
                        </>
                      ) : (
                        <>
                          <div className="flex items-center gap-3">
                            <Badge
                              variant={query.enabled ? 'default' : 'secondary'}
                              className={
                                query.enabled ? 'bg-green-500 text-white' : ''
                              }
                            >
                              {query.enabled ? 'Enabled' : 'Disabled'}
                            </Badge>
                            <span>{query.query_text}</span>
                            {query.run_count > 0 && (
                              <span className="text-xs text-muted-foreground">
                                ({query.run_count} runs)
                              </span>
                            )}
                          </div>
                          <div className="flex items-center gap-2">
                            <Button
                              size="sm"
                              variant="ghost"
                              onClick={() => startEditing(query)}
                              aria-label="Edit query"
                            >
                              <Edit2 className="h-4 w-4" />
                            </Button>
                            {query.enabled ? (
                              <Button
                                size="sm"
                                variant="outline"
                                onClick={() => disableMutation.mutate(query.id)}
                                disabled={disableMutation.isPending}
                                aria-label="Disable query"
                              >
                                <X className="h-4 w-4" />
                              </Button>
                            ) : (
                              <Button
                                size="sm"
                                variant="outline"
                                onClick={() => enableMutation.mutate(query.id)}
                                disabled={enableMutation.isPending}
                                aria-label="Enable query"
                              >
                                <Check className="h-4 w-4" />
                              </Button>
                            )}
                            <Button
                              size="sm"
                              variant="ghost"
                              className="text-destructive"
                              onClick={() => {
                                setQueryToDelete(query.id)
                                setDeleteDialogOpen(true)
                              }}
                              disabled={deleteMutation.isPending}
                              aria-label="Delete query"
                            >
                              <Trash2 className="h-4 w-4" />
                            </Button>
                          </div>
                        </>
                      )}
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>
          ))}
      </div>

      <ConfirmDialog
        open={deleteDialogOpen}
        title="Delete Query"
        description="Are you sure you want to delete this query? This action cannot be undone."
        confirmLabel="Delete"
        variant="destructive"
        onConfirm={() => {
          if (queryToDelete) deleteMutation.mutate(queryToDelete)
          setDeleteDialogOpen(false)
          setQueryToDelete(null)
        }}
        onCancel={() => {
          setDeleteDialogOpen(false)
          setQueryToDelete(null)
        }}
      />
    </div>
  )
}
