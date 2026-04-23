'use client'

import { useState, useCallback } from 'react'
import { ImageDropzone } from './ImageDropzone'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Badge } from '@/components/ui/badge'
import { Separator } from '@/components/ui/separator'
import { Plus, X, Calendar, MapPin, Users, Ticket, Image as ImageIcon } from 'lucide-react'

interface EventDate {
  start?: string
  end?: string
  location_description?: string
  lineup?: string[]
  ticket_url?: string
  size?: number
}

interface MediaItem {
  url: string
  caption?: string
}

interface FestivalPayload {
  name?: string
  description?: string
  full_description?: string
  website_url?: string
  youtube_url?: string
  logo_url?: string
  media_items?: MediaItem[]
  tags?: string[]
  event_dates?: EventDate[]
}

interface FestivalEditFormProps {
  initialData?: FestivalPayload
  onChange: (data: FestivalPayload) => void
}

export function FestivalEditForm({ initialData = {}, onChange }: FestivalEditFormProps) {
  const [data, setData] = useState<FestivalPayload>({
    name: '',
    description: '',
    full_description: '',
    website_url: '',
    youtube_url: '',
    logo_url: '',
    media_items: [],
    tags: [],
    event_dates: [],
    ...initialData,
  })

  const [newTag, setNewTag] = useState('')
  const [newLineup, setNewLineup] = useState('')

  const updateField = useCallback(<K extends keyof FestivalPayload>(
    field: K,
    value: FestivalPayload[K]
  ) => {
    const newData = { ...data, [field]: value }
    setData(newData)
    onChange(newData)
  }, [data, onChange])

  const handleLogoChange = (base64Image: string | undefined) => {
    updateField('logo_url', base64Image || '')
  }

  const addTag = () => {
    if (newTag.trim() && !data.tags?.includes(newTag.trim())) {
      const newTags = [...(data.tags || []), newTag.trim()]
      updateField('tags', newTags)
      setNewTag('')
    }
  }

  const removeTag = (tag: string) => {
    const newTags = data.tags?.filter(t => t !== tag) || []
    updateField('tags', newTags)
  }

  const addEventDate = () => {
    const newEventDates = [
      ...(data.event_dates || []),
      {
        start: '',
        end: '',
        location_description: '',
        lineup: [],
        ticket_url: '',
        size: undefined,
      },
    ]
    updateField('event_dates', newEventDates)
  }

  const updateEventDate = (index: number, field: keyof EventDate, value: any) => {
    const newEventDates = [...(data.event_dates || [])]
    newEventDates[index] = { ...newEventDates[index], [field]: value }
    updateField('event_dates', newEventDates)
  }

  const removeEventDate = (index: number) => {
    const newEventDates = data.event_dates?.filter((_, i) => i !== index) || []
    updateField('event_dates', newEventDates)
  }

  const addLineupArtist = (dateIndex: number) => {
    if (newLineup.trim()) {
      const artists = newLineup.split(',').map(a => a.trim()).filter(Boolean)
      const currentLineup = data.event_dates?.[dateIndex]?.lineup || []
      const newLineupList = [...currentLineup, ...artists]
      updateEventDate(dateIndex, 'lineup', newLineupList)
      setNewLineup('')
    }
  }

  const removeLineupArtist = (dateIndex: number, artist: string) => {
    const currentLineup = data.event_dates?.[dateIndex]?.lineup || []
    const newLineupList = currentLineup.filter(a => a !== artist)
    updateEventDate(dateIndex, 'lineup', newLineupList)
  }

  const addMediaItem = () => {
    const newMediaItems = [
      ...(data.media_items || []),
      { url: '', caption: '' },
    ]
    updateField('media_items', newMediaItems)
  }

  const updateMediaItem = (index: number, field: keyof MediaItem, value: string) => {
    const newMediaItems = [...(data.media_items || [])]
    newMediaItems[index] = { ...newMediaItems[index], [field]: value }
    updateField('media_items', newMediaItems)
  }

  const removeMediaItem = (index: number) => {
    const newMediaItems = data.media_items?.filter((_, i) => i !== index) || []
    updateField('media_items', newMediaItems)
  }

  return (
    <Tabs defaultValue="basic" className="w-full">
      <TabsList className="grid w-full grid-cols-4">
        <TabsTrigger value="basic">Basic Info</TabsTrigger>
        <TabsTrigger value="media">Media</TabsTrigger>
        <TabsTrigger value="dates">
          Dates ({data.event_dates?.length || 0})
        </TabsTrigger>
        <TabsTrigger value="tags">Tags ({data.tags?.length || 0})</TabsTrigger>
      </TabsList>

      {/* Basic Info Tab */}
      <TabsContent value="basic" className="space-y-4">
        <div className="space-y-2">
          <Label htmlFor="name">Festival Name *</Label>
          <Input
            id="name"
            value={data.name}
            onChange={(e) => updateField('name', e.target.value)}
            placeholder="e.g., Coachella 2026"
          />
        </div>

        <div className="space-y-2">
          <Label htmlFor="description">Short Description</Label>
          <Textarea
            id="description"
            value={data.description}
            onChange={(e) => updateField('description', e.target.value)}
            placeholder="Brief description (10+ chars recommended)"
            rows={2}
          />
        </div>

        <div className="space-y-2">
          <Label htmlFor="full_description">Full Description</Label>
          <Textarea
            id="full_description"
            value={data.full_description}
            onChange={(e) => updateField('full_description', e.target.value)}
            placeholder="Detailed description (20+ chars recommended)"
            rows={4}
          />
        </div>

        <div className="grid grid-cols-2 gap-4">
          <div className="space-y-2">
            <Label htmlFor="website_url">Website URL</Label>
            <Input
              id="website_url"
              value={data.website_url}
              onChange={(e) => updateField('website_url', e.target.value)}
              placeholder="https://..."
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="youtube_url">YouTube URL</Label>
            <Input
              id="youtube_url"
              value={data.youtube_url}
              onChange={(e) => updateField('youtube_url', e.target.value)}
              placeholder="https://youtube.com/..."
            />
          </div>
        </div>
      </TabsContent>

      {/* Media Tab */}
      <TabsContent value="media" className="space-y-4">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <ImageIcon className="h-5 w-5" />
              Logo *
            </CardTitle>
          </CardHeader>
          <CardContent>
            <ImageDropzone
              value={data.logo_url}
              onChange={handleLogoChange}
              label="Drop logo image here or click to browse"
            />
            {data.logo_url && (
              <p className="text-sm text-green-600 mt-2 flex items-center gap-1">
                ✓ Logo selected
              </p>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between">
            <CardTitle>Gallery Images</CardTitle>
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={addMediaItem}
            >
              <Plus className="h-4 w-4 mr-1" />
              Add Image
            </Button>
          </CardHeader>
          <CardContent className="space-y-4">
            {data.media_items?.map((item, index) => (
              <div key={index} className="flex gap-2 items-start">
                <div className="flex-1 space-y-2">
                  <Input
                    value={item.url}
                    onChange={(e) => updateMediaItem(index, 'url', e.target.value)}
                    placeholder="Image URL"
                  />
                  <Input
                    value={item.caption || ''}
                    onChange={(e) => updateMediaItem(index, 'caption', e.target.value)}
                    placeholder="Caption (optional)"
                  />
                </div>
                <Button
                  type="button"
                  variant="ghost"
                  size="icon"
                  onClick={() => removeMediaItem(index)}
                >
                  <X className="h-4 w-4" />
                </Button>
              </div>
            ))}
            {(!data.media_items || data.media_items.length === 0) && (
              <p className="text-sm text-muted-foreground text-center py-4">
                No gallery images added yet
              </p>
            )}
          </CardContent>
        </Card>
      </TabsContent>

      {/* Dates Tab */}
      <TabsContent value="dates" className="space-y-4">
        <div className="flex justify-between items-center">
          <h3 className="text-sm font-medium text-muted-foreground">
            Event Dates
          </h3>
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={addEventDate}
          >
            <Plus className="h-4 w-4 mr-1" />
            Add Date
          </Button>
        </div>

        {data.event_dates?.map((date, index) => (
          <Card key={index}>
            <CardHeader className="flex flex-row items-center justify-between pb-2">
              <CardTitle className="text-base flex items-center gap-2">
                <Calendar className="h-4 w-4" />
                Event Date #{index + 1}
              </CardTitle>
              <Button
                type="button"
                variant="ghost"
                size="icon"
                onClick={() => removeEventDate(index)}
              >
                <X className="h-4 w-4" />
              </Button>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label>Start Date *</Label>
                  <Input
                    type="datetime-local"
                    value={date.start ? date.start.slice(0, 16) : ''}
                    onChange={(e) => {
                      // Ensure ISO 8601 format with seconds: "2026-07-15T14:00:00"
                      const value = e.target.value ? `${e.target.value}:00` : ''
                      updateEventDate(index, 'start', value)
                    }}
                  />
                </div>
                <div className="space-y-2">
                  <Label>End Date</Label>
                  <Input
                    type="datetime-local"
                    value={date.end ? date.end.slice(0, 16) : ''}
                    onChange={(e) => {
                      // Ensure ISO 8601 format with seconds: "2026-07-15T14:00:00"
                      const value = e.target.value ? `${e.target.value}:00` : ''
                      updateEventDate(index, 'end', value)
                    }}
                  />
                </div>
              </div>

              <div className="space-y-2">
                <Label className="flex items-center gap-2">
                  <MapPin className="h-4 w-4" />
                  Location Description *
                </Label>
                <Input
                  value={date.location_description || ''}
                  onChange={(e) => updateEventDate(index, 'location_description', e.target.value)}
                  placeholder="e.g., Empire Polo Club, Indio, CA"
                />
              </div>

              <div className="space-y-2">
                <Label className="flex items-center gap-2">
                  <Users className="h-4 w-4" />
                  Lineup
                </Label>
                <div className="flex gap-2">
                  <Input
                    value={newLineup}
                    onChange={(e) => setNewLineup(e.target.value)}
                    placeholder="Add artists (comma-separated)"
                    onKeyDown={(e) => {
                      if (e.key === 'Enter') {
                        e.preventDefault()
                        addLineupArtist(index)
                      }
                    }}
                  />
                  <Button
                    type="button"
                    variant="outline"
                    onClick={() => addLineupArtist(index)}
                  >
                    <Plus className="h-4 w-4" />
                  </Button>
                </div>
                <div className="flex flex-wrap gap-1 mt-2">
                  {date.lineup?.map((artist) => (
                    <Badge
                      key={artist}
                      variant="secondary"
                      className="cursor-pointer hover:bg-red-100"
                      onClick={() => removeLineupArtist(index, artist)}
                    >
                      {artist} ×
                    </Badge>
                  ))}
                </div>
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label className="flex items-center gap-2">
                    <Ticket className="h-4 w-4" />
                    Ticket URL
                  </Label>
                  <Input
                    value={date.ticket_url || ''}
                    onChange={(e) => updateEventDate(index, 'ticket_url', e.target.value)}
                    placeholder="https://..."
                  />
                </div>
                <div className="space-y-2">
                  <Label>Expected Size</Label>
                  <Input
                    type="number"
                    value={date.size || ''}
                    onChange={(e) => updateEventDate(index, 'size', parseInt(e.target.value) || undefined)}
                    placeholder="e.g., 50000"
                  />
                </div>
              </div>
            </CardContent>
          </Card>
        ))}

        {(!data.event_dates || data.event_dates.length === 0) && (
          <div className="text-center py-8 border-2 border-dashed rounded-lg">
            <Calendar className="h-8 w-8 mx-auto text-muted-foreground mb-2" />
            <p className="text-sm text-muted-foreground">
              No event dates added yet
            </p>
            <Button
              type="button"
              variant="outline"
              size="sm"
              className="mt-2"
              onClick={addEventDate}
            >
              <Plus className="h-4 w-4 mr-1" />
              Add First Date
            </Button>
          </div>
        )}
      </TabsContent>

      {/* Tags Tab */}
      <TabsContent value="tags" className="space-y-4">
        <div className="space-y-2">
          <Label>Add Tags</Label>
          <div className="flex gap-2">
            <Input
              value={newTag}
              onChange={(e) => setNewTag(e.target.value)}
              placeholder="Enter tag name"
              onKeyDown={(e) => {
                if (e.key === 'Enter') {
                  e.preventDefault()
                  addTag()
                }
              }}
            />
            <Button
              type="button"
              variant="outline"
              onClick={addTag}
            >
              <Plus className="h-4 w-4" />
            </Button>
          </div>
          <p className="text-xs text-muted-foreground">
            Press Enter or click + to add. Click a tag to remove it.
          </p>
        </div>

        <Separator />

        <div className="space-y-2">
          <Label>Current Tags ({data.tags?.length || 0})</Label>
          <div className="flex flex-wrap gap-2">
            {data.tags?.map((tag) => (
              <Badge
                key={tag}
                variant="secondary"
                className="cursor-pointer hover:bg-red-100 text-sm py-1 px-3"
                onClick={() => removeTag(tag)}
              >
                {tag} ×
              </Badge>
            ))}
            {(!data.tags || data.tags.length === 0) && (
              <p className="text-sm text-muted-foreground">
                No tags added yet
              </p>
            )}
          </div>
        </div>

        <Separator />

        <div className="bg-muted p-4 rounded-lg">
          <p className="text-sm font-medium mb-2">Popular Tags</p>
          <div className="flex flex-wrap gap-2">
            {['music', 'festival', 'edm', 'rock', 'indie', 'electronic', 'outdoor', 'camping', 'food', 'art'].map((tag) => (
              <Badge
                key={tag}
                variant="outline"
                className={`cursor-pointer ${data.tags?.includes(tag) ? 'opacity-50' : ''}`}
                onClick={() => {
                  if (!data.tags?.includes(tag)) {
                    updateField('tags', [...(data.tags || []), tag])
                  }
                }}
              >
                {tag}
              </Badge>
            ))}
          </div>
        </div>
      </TabsContent>
    </Tabs>
  )
}
