'use client'

import { useState, useRef, useEffect, useMemo } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  getQueries,
  createQuery,
  updateQuery,
  deleteQuery,
  deleteAllQueries,
  enableQuery,
  disableQuery,
} from '@/lib/api'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Select } from '@/components/ui/select'
import {
  Check,
  X,
  Plus,
  Trash2,
  Edit2,
  Save,
  Sparkles,
  ChevronDown,
  Globe,
  Building2,
} from 'lucide-react'
import { ConfirmDialog } from '@/components/ui/dialog-confirm'
import { SkeletonCard } from '@/components/ui/skeleton'
import { querySchema } from '@/lib/validation'
import { useToast } from '@/components/ui/toast-provider'

const CURRENT_YEAR = new Date().getFullYear()

// Pre-populated locations: countries + popular party cities
const PRESET_LOCATIONS = [
  // Countries
  'Germany',
  'Netherlands',
  'France',
  'Spain',
  'Portugal',
  'Italy',
  'United Kingdom',
  'Belgium',
  'Switzerland',
  'Austria',
  'Czech Republic',
  'Hungary',
  'Poland',
  'Sweden',
  'Norway',
  'Denmark',
  'Finland',
  'United States',
  'Canada',
  'Mexico',
  'Brazil',
  'Argentina',
  'Australia',
  'New Zealand',
  'Japan',
  'Thailand',
  'India',
  'South Africa',
  'Morocco',
  'Israel',
  'Turkey',
  'Greece',
  'Croatia',
  'Serbia',
  'Romania',
  'Bulgaria',
  'Slovakia',
  'Slovenia',
  'Estonia',
  'Latvia',
  'Lithuania',
  'Ukraine',
  'Russia',
  'China',
  'Indonesia',
  'Malaysia',
  'Philippines',
  'Vietnam',
  'Colombia',
  'Chile',
  'Peru',
  'Ecuador',
  // Popular party cities
  'Berlin',
  'Barcelona',
  'Amsterdam',
  'Ibiza',
  'London',
  'Paris',
  'Miami',
  'Las Vegas',
  'New York',
  'Los Angeles',
  'San Francisco',
  'Chicago',
  'Austin',
  'Tulum',
  'Cancun',
  'Rio de Janeiro',
  'São Paulo',
  'Bangkok',
  'Bali',
  'Tel Aviv',
  'Beirut',
  'Dubai',
  'Cape Town',
  'Lisbon',
  'Madrid',
  'Valencia',
  'Milan',
  'Rome',
  'Zurich',
  'Vienna',
  'Prague',
  'Budapest',
  'Warsaw',
  'Stockholm',
  'Oslo',
  'Copenhagen',
  'Helsinki',
  'Melbourne',
  'Sydney',
  'Tokyo',
  'Seoul',
  'Singapore',
  'Hong Kong',
  'Istanbul',
  'Athens',
  'Split',
  'Belgrade',
  'Bucharest',
  'Sofia',
  'Bratislava',
  'Ljubljana',
  'Tallinn',
  'Riga',
  'Vilnius',
  'Kyiv',
  'Moscow',
  'Shanghai',
  'Jakarta',
  'Kuala Lumpur',
  'Manila',
  'Ho Chi Minh City',
  'Bogotá',
  'Santiago',
  'Lima',
  'Quito',
]

function CreatableLocationSelect({
  selected,
  onChange,
}: {
  selected: string[]
  onChange: (values: string[]) => void
}) {
  const [inputValue, setInputValue] = useState('')
  const [isOpen, setIsOpen] = useState(false)
  const containerRef = useRef<HTMLDivElement>(null)

  // Close dropdown when clicking outside
  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setIsOpen(false)
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [])

  const filtered = useMemo(() => {
    const query = inputValue.toLowerCase().trim()
    if (!query) return PRESET_LOCATIONS.filter((l) => !selected.includes(l))
    return PRESET_LOCATIONS.filter(
      (l) =>
        !selected.includes(l) && l.toLowerCase().includes(query)
    )
  }, [inputValue, selected])

  const canAddCustom =
    inputValue.trim() &&
    !selected.includes(inputValue.trim()) &&
    !PRESET_LOCATIONS.some(
      (l) => l.toLowerCase() === inputValue.trim().toLowerCase()
    )

  const addLocation = (loc: string) => {
    const trimmed = loc.trim()
    if (!trimmed || selected.includes(trimmed)) return
    onChange([...selected, trimmed])
    setInputValue('')
    // Keep dropdown open for multi-select
  }

  const removeLocation = (loc: string) => {
    onChange(selected.filter((s) => s !== loc))
  }

  return (
    <div ref={containerRef} className="relative flex-1">
      {/* Selected chips + input */}
      <div
        className="flex flex-wrap items-center gap-1.5 rounded-md border bg-background px-2 py-1.5 min-h-[2.5rem] cursor-text"
        onClick={() => {
          const input = containerRef.current?.querySelector('input')
          input?.focus()
          setIsOpen(true)
        }}
      >
        {selected.map((loc) => (
          <Badge
            key={loc}
            variant="secondary"
            className="flex items-center gap-1 pl-2 pr-1 text-sm"
          >
            {loc}
            <button
              onClick={(e) => {
                e.stopPropagation()
                removeLocation(loc)
              }}
              className="rounded-sm hover:bg-muted p-0.5"
            >
              <X className="h-3 w-3" />
            </button>
          </Badge>
        ))}
        <input
          type="text"
          value={inputValue}
          onChange={(e) => {
            setInputValue(e.target.value)
            setIsOpen(true)
          }}
          onFocus={() => setIsOpen(true)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') {
              e.preventDefault()
              if (canAddCustom) {
                addLocation(inputValue)
              } else if (filtered.length > 0) {
                addLocation(filtered[0])
              }
            }
            if (e.key === 'Backspace' && !inputValue && selected.length > 0) {
              removeLocation(selected[selected.length - 1])
            }
            if (e.key === 'Escape') {
              setIsOpen(false)
            }
          }}
          placeholder={selected.length === 0 ? 'Type or select locations...' : ''}
          className="flex-1 min-w-[8rem] bg-transparent outline-none text-sm py-0.5"
        />
        <ChevronDown className="h-4 w-4 text-muted-foreground shrink-0" />
      </div>

      {/* Dropdown */}
      {isOpen && (
        <div className="absolute z-50 mt-1 w-full max-h-60 overflow-y-auto rounded-md border bg-popover shadow-md">
          {canAddCustom && (
            <button
              className="w-full text-left px-3 py-2 text-sm hover:bg-accent flex items-center gap-2"
              onClick={() => addLocation(inputValue)}
            >
              <Plus className="h-3.5 w-3.5" />
              Add &quot;{inputValue.trim()}&quot;
            </button>
          )}
          {filtered.length === 0 && !canAddCustom && (
            <div className="px-3 py-2 text-sm text-muted-foreground">
              No locations found
            </div>
          )}
          {filtered.map((loc) => {
            const isCity = ![
              'Germany', 'Netherlands', 'France', 'Spain', 'Portugal', 'Italy',
              'United Kingdom', 'Belgium', 'Switzerland', 'Austria', 'Czech Republic',
              'Hungary', 'Poland', 'Sweden', 'Norway', 'Denmark', 'Finland',
              'United States', 'Canada', 'Mexico', 'Brazil', 'Argentina',
              'Australia', 'New Zealand', 'Japan', 'Thailand', 'India',
              'South Africa', 'Morocco', 'Israel', 'Turkey', 'Greece',
              'Croatia', 'Serbia', 'Romania', 'Bulgaria', 'Slovakia',
              'Slovenia', 'Estonia', 'Latvia', 'Lithuania', 'Ukraine',
              'Russia', 'China', 'Indonesia', 'Malaysia', 'Philippines',
              'Vietnam', 'Colombia', 'Chile', 'Peru', 'Ecuador',
            ].includes(loc)
            return (
              <button
                key={loc}
                className="w-full text-left px-3 py-2 text-sm hover:bg-accent flex items-center gap-2"
                onClick={() => addLocation(loc)}
              >
                {isCity ? (
                  <Building2 className="h-3.5 w-3.5 text-muted-foreground shrink-0" />
                ) : (
                  <Globe className="h-3.5 w-3.5 text-muted-foreground shrink-0" />
                )}
                {loc}
              </button>
            )
          })}
        </div>
      )}
    </div>
  )
}

export default function QueriesPage() {
  const queryClient = useQueryClient()
  const { success, error: toastError } = useToast()

  // Single add state
  const [newQuery, setNewQuery] = useState('')
  const [newCategory, setNewCategory] = useState('general')
  const [queryError, setQueryError] = useState<string | null>(null)

  // Bulk add state
  const [bulkPrefix, setBulkPrefix] = useState('festivals in')
  const [bulkLocations, setBulkLocations] = useState<string[]>([])
  const [bulkYear, setBulkYear] = useState(String(CURRENT_YEAR))
  const [bulkCategory, setBulkCategory] = useState('country')
  const [bulkPreviewOpen, setBulkPreviewOpen] = useState(false)

  // Edit state
  const [editing, setEditing] = useState<string | null>(null)
  const [editValues, setEditValues] = useState({ query_text: '', category: '' })

  // Delete state
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false)
  const [queryToDelete, setQueryToDelete] = useState<string | null>(null)
  const [deleteAllDialogOpen, setDeleteAllDialogOpen] = useState(false)

  const { data: queries, isLoading } = useQuery({
    queryKey: ['queries'],
    queryFn: () => getQueries(),
  })

  const createMutation = useMutation({
    mutationFn: (params: { queryText: string; category: string }) =>
      createQuery(params.queryText, params.category),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['queries'] })
    },
  })

  const bulkCreateMutation = useMutation({
    mutationFn: async (items: { queryText: string; category: string }[]) => {
      // Fire all creates in parallel
      await Promise.all(
        items.map((item) => createQuery(item.queryText, item.category))
      )
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['queries'] })
      success(`Created ${bulkLocations.length} queries`)
      setBulkLocations([])
      setBulkPreviewOpen(false)
    },
    onError: () => {
      toastError('Some queries failed to create')
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

  const deleteAllMutation = useMutation({
    mutationFn: deleteAllQueries,
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['queries'] })
      success(`Deleted ${data.count} queries`)
      setDeleteAllDialogOpen(false)
    },
    onError: () => {
      toastError('Failed to delete all queries')
    },
  })

  const enableMutation = useMutation({
    mutationFn: enableQuery,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['queries'] }),
  })

  const disableMutation = useMutation({
    mutationFn: disableQuery,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['queries'] }),
  })

  const handleSingleCreate = () => {
    const result = querySchema.safeParse({ query_text: newQuery, category: newCategory })
    if (!result.success) {
      setQueryError(result.error.issues[0]?.message || 'Invalid input')
      return
    }
    setQueryError(null)
    createMutation.mutate(
      { queryText: newQuery, category: newCategory },
      {
        onSuccess: () => {
          setNewQuery('')
          success('Query added')
        },
        onError: () => toastError('Failed to add query'),
      }
    )
  }

  const handleBulkCreate = () => {
    if (bulkLocations.length === 0) return
    const items = bulkLocations.map((loc) => ({
      queryText: `${bulkPrefix} ${loc} ${bulkYear}`.trim(),
      category: bulkCategory,
    }))
    bulkCreateMutation.mutate(items)
  }

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

  const groupedQueries = queries?.reduce(
    (acc, query) => {
      if (!acc[query.category]) acc[query.category] = []
      acc[query.category].push(query)
      return acc
    },
    {} as Record<string, NonNullable<typeof queries>>
  )

  const generatedQueries = useMemo(() => {
    return bulkLocations.map((loc) => `${bulkPrefix} ${loc} ${bulkYear}`.trim())
  }, [bulkLocations, bulkPrefix, bulkYear])

  if (isLoading) {
    return (
      <div className="space-y-6">
        <h1 className="text-2xl sm:text-3xl font-bold">Discovery Queries</h1>
        <SkeletonCard className="h-32" />
        <SkeletonCard className="h-48" />
        <SkeletonCard className="h-64" />
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
        <h1 className="text-2xl sm:text-3xl font-bold">Discovery Queries</h1>
        {queries && queries.length > 0 && (
          <Button
            variant="destructive"
            size="sm"
            onClick={() => setDeleteAllDialogOpen(true)}
            disabled={deleteAllMutation.isPending}
          >
            <Trash2 className="h-4 w-4 mr-2" />
            Delete All ({queries.length})
          </Button>
        )}
      </div>

      {/* Bulk Add */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Sparkles className="h-5 w-5 text-yellow-500" />
            Bulk Add Queries
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex flex-col gap-3">
            {/* Prefix + Year row */}
            <div className="flex flex-col sm:flex-row gap-3">
              <div className="flex-1">
                <label className="text-sm font-medium text-muted-foreground mb-1.5 block">
                  Prefix
                </label>
                <Input
                  value={bulkPrefix}
                  onChange={(e) => setBulkPrefix(e.target.value)}
                  placeholder="festivals in"
                />
              </div>
              <div>
                <label className="text-sm font-medium text-muted-foreground mb-1.5 block">
                  Year
                </label>
                <Select
                  value={bulkYear}
                  onChange={(e) => setBulkYear(e.target.value)}
                  className="w-full sm:w-28"
                >
                  {Array.from({ length: 5 }, (_, i) => CURRENT_YEAR + i).map(
                    (y) => (
                      <option key={y} value={String(y)}>
                        {y}
                      </option>
                    )
                  )}
                </Select>
              </div>
              <div>
                <label className="text-sm font-medium text-muted-foreground mb-1.5 block">
                  Category
                </label>
                <Select
                  value={bulkCategory}
                  onChange={(e) => setBulkCategory(e.target.value)}
                  className="w-full sm:w-36"
                >
                  <option value="general">General</option>
                  <option value="country">Country</option>
                  <option value="city">City</option>
                  <option value="genre">Genre</option>
                </Select>
              </div>
            </div>

            {/* Location multiselect */}
            <div>
              <label className="text-sm font-medium text-muted-foreground mb-1.5 block">
                Locations ({bulkLocations.length} selected)
              </label>
              <CreatableLocationSelect
                selected={bulkLocations}
                onChange={setBulkLocations}
              />
              <p className="text-xs text-muted-foreground mt-1.5">
                Type a location and press Enter, or pick from the dropdown.
                Includes countries and popular party cities.
              </p>
            </div>

            {/* Preview + Add */}
            {generatedQueries.length > 0 && (
              <div className="space-y-2">
                <button
                  onClick={() => setBulkPreviewOpen(!bulkPreviewOpen)}
                  className="text-sm text-muted-foreground hover:text-foreground flex items-center gap-1"
                >
                  <ChevronDown
                    className={`h-4 w-4 transition-transform ${
                      bulkPreviewOpen ? 'rotate-180' : ''
                    }`}
                  />
                  {bulkPreviewOpen ? 'Hide' : 'Show'} preview ({generatedQueries.length} queries)
                </button>
                {bulkPreviewOpen && (
                  <div className="rounded-md border bg-muted/30 p-3 space-y-1 max-h-48 overflow-y-auto">
                    {generatedQueries.map((q, i) => (
                      <div key={i} className="text-sm font-mono text-muted-foreground">
                        {q}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}

            <div className="flex justify-end">
              <Button
                onClick={handleBulkCreate}
                disabled={
                  bulkLocations.length === 0 || bulkCreateMutation.isPending
                }
              >
                <Plus className="h-4 w-4 mr-2" />
                Add {bulkLocations.length > 0 ? `${bulkLocations.length} Queries` : 'Queries'}
              </Button>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Single Add */}
      <Card>
        <CardHeader>
          <CardTitle>Add Single Query</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex flex-col gap-2">
            <div className="flex flex-col sm:flex-row gap-3">
              <Input
                placeholder="Query text (e.g., 'electronic music festivals in Berlin')"
                value={newQuery}
                onChange={(e) => {
                  setNewQuery(e.target.value)
                  setQueryError(null)
                }}
                className="flex-1"
                aria-invalid={!!queryError}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') handleSingleCreate()
                }}
              />
              <Select
                value={newCategory}
                onChange={(e) => setNewCategory(e.target.value)}
                className="w-full sm:w-40"
              >
                <option value="general">General</option>
                <option value="country">Country</option>
                <option value="city">City</option>
                <option value="genre">Genre</option>
              </Select>
              <Button
                onClick={handleSingleCreate}
                disabled={createMutation.isPending}
                className="shrink-0"
              >
                <Plus className="h-4 w-4 mr-2" />
                Add Query
              </Button>
            </div>
            {queryError && (
              <p className="text-sm text-destructive">{queryError}</p>
            )}
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
                      className="flex flex-col sm:flex-row sm:items-center sm:justify-between rounded-lg border p-3 gap-2 sm:gap-0"
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
                          <div className="flex items-center gap-3 min-w-0">
                            <Badge
                              variant={query.enabled ? 'default' : 'secondary'}
                              className={
                                query.enabled ? 'bg-green-500 text-white' : ''
                              }
                            >
                              {query.enabled ? 'Enabled' : 'Disabled'}
                            </Badge>
                            <span className="truncate">{query.query_text}</span>
                            {query.run_count > 0 && (
                              <span className="text-xs text-muted-foreground shrink-0">
                                ({query.run_count} runs)
                              </span>
                            )}
                          </div>
                          <div className="flex items-center gap-2 shrink-0">
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

      {/* Delete single dialog */}
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

      {/* Delete all dialog */}
      <ConfirmDialog
        open={deleteAllDialogOpen}
        title="Delete All Queries"
        description={`Are you sure you want to delete all ${queries?.length ?? 0} queries? This action cannot be undone.`}
        confirmLabel="Delete All"
        variant="destructive"
        onConfirm={() => deleteAllMutation.mutate()}
        onCancel={() => setDeleteAllDialogOpen(false)}
      />
    </div>
  )
}
