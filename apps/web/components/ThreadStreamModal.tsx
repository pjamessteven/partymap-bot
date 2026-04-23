'use client'

import { useEffect, useRef, useState, useCallback } from 'react'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Separator } from '@/components/ui/separator'
import { Loader2, X, Wifi, WifiOff, Bot, MessageSquare, Wrench, Lightbulb, ExternalLink, Clock, DollarSign, BarChart3 } from 'lucide-react'
import { cn, formatRelativeTime, formatCurrency } from '@/lib/utils'
import { useQuery } from '@tanstack/react-query'
import { getThread, getThreadEvents } from '@/lib/api'
import type { Thread } from '@/lib/api'
import Link from 'next/link'

interface ThreadStreamModalProps {
  threadId: string
  onClose: () => void
}

interface StreamEvent {
  id: string
  type: 'message' | 'tool' | 'reasoning' | 'custom' | 'error' | 'end' | 'metadata'
  content: unknown
  timestamp: string
}

interface ThreadEvent {
  id: string
  event_type: string
  event_data: unknown
  timestamp: string
  step_number?: number
  node_name?: string
  tool_name?: string
}

export function ThreadStreamModal({ threadId, onClose }: ThreadStreamModalProps) {
  const [events, setEvents] = useState<StreamEvent[]>([])
  const [isConnected, setIsConnected] = useState(false)
  const [isLoading, setIsLoading] = useState(true)
  const scrollRef = useRef<HTMLDivElement>(null)
  const eventSourceRef = useRef<EventSource | null>(null)
  const hasLoadedHistory = useRef(false)

  // Fetch thread metadata
  const { data: thread } = useQuery<Thread>({
    queryKey: ['thread', threadId],
    queryFn: () => getThread(threadId),
  })

  // Fetch historical events first
  const { data: historicalEvents } = useQuery<{ events: ThreadEvent[] }>({
    queryKey: ['thread-events', threadId],
    queryFn: () => getThreadEvents(threadId),
    enabled: !!threadId,
  })

  // Convert historical events to stream format
  useEffect(() => {
    if (historicalEvents?.events && !hasLoadedHistory.current) {
      hasLoadedHistory.current = true
      const convertedEvents: StreamEvent[] = historicalEvents.events.map((event, index) => ({
        id: `hist-${event.id || index}`,
        type: convertEventType(event.event_type),
        content: event.event_data,
        timestamp: event.timestamp || new Date().toISOString(),
      }))
      setEvents(convertedEvents)
      setIsLoading(false)
    }
  }, [historicalEvents])

  // Connect to SSE stream
  useEffect(() => {
    if (!threadId) return

    // Only connect if thread is running
    if (thread?.status !== 'running') {
      setIsLoading(false)
      return
    }

    const eventSource = new EventSource(`/api/threads/${threadId}/runs/stream`)
    eventSourceRef.current = eventSource

    eventSource.onopen = () => {
      setIsConnected(true)
      setIsLoading(false)
    }

    eventSource.addEventListener('metadata', (e) => {
      try {
        const data = JSON.parse(e.data)
        setEvents((prev) => [
          ...prev,
          {
            id: `meta-${Date.now()}`,
            type: 'metadata',
            content: data,
            timestamp: new Date().toISOString(),
          },
        ])
      } catch {
        // Ignore parse errors
      }
    })

    eventSource.addEventListener('messages', (e) => {
      try {
        const data = JSON.parse(e.data)
        setEvents((prev) => [
          ...prev,
          {
            id: `msg-${Date.now()}-${Math.random()}`,
            type: 'message',
            content: data,
            timestamp: new Date().toISOString(),
          },
        ])
      } catch {
        // Ignore parse errors
      }
    })

    eventSource.addEventListener('tools', (e) => {
      try {
        const data = JSON.parse(e.data)
        setEvents((prev) => [
          ...prev,
          {
            id: `tool-${Date.now()}-${Math.random()}`,
            type: 'tool',
            content: data,
            timestamp: new Date().toISOString(),
          },
        ])
      } catch {
        // Ignore parse errors
      }
    })

    eventSource.addEventListener('custom', (e) => {
      try {
        const data = JSON.parse(e.data)
        setEvents((prev) => [
          ...prev,
          {
            id: `custom-${Date.now()}-${Math.random()}`,
            type: data.type === 'reasoning' ? 'reasoning' : 'custom',
            content: data,
            timestamp: new Date().toISOString(),
          },
        ])
      } catch {
        // Ignore parse errors
      }
    })

    eventSource.addEventListener('error', (e) => {
      try {
        const msgEvent = e as MessageEvent
        const data = msgEvent.data ? JSON.parse(msgEvent.data) : { message: 'Connection error' }
        setEvents((prev) => [
          ...prev,
          {
            id: `error-${Date.now()}`,
            type: 'error',
            content: data,
            timestamp: new Date().toISOString(),
          },
        ])
      } catch {
        // Ignore parse errors
      }
    })

    eventSource.addEventListener('end', () => {
      setIsConnected(false)
      eventSource.close()
    })

    eventSource.onerror = () => {
      setIsConnected(false)
    }

    return () => {
      eventSource.close()
    }
  }, [threadId, thread?.status])

  // Auto-scroll to bottom
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight
    }
  }, [events])

  const getEventIcon = (type: StreamEvent['type']) => {
    switch (type) {
      case 'message':
        return <MessageSquare className="h-4 w-4" />
      case 'tool':
        return <Wrench className="h-4 w-4" />
      case 'reasoning':
        return <Lightbulb className="h-4 w-4" />
      case 'error':
        return <X className="h-4 w-4 text-destructive" />
      default:
        return <Bot className="h-4 w-4" />
    }
  }

  const getEventColor = (type: StreamEvent['type']) => {
    switch (type) {
      case 'message':
        return 'bg-blue-500/10 text-blue-600 border-blue-500/20'
      case 'tool':
        return 'bg-amber-500/10 text-amber-600 border-amber-500/20'
      case 'reasoning':
        return 'bg-purple-500/10 text-purple-600 border-purple-500/20'
      case 'error':
        return 'bg-destructive/10 text-destructive border-destructive/20'
      default:
        return 'bg-muted text-muted-foreground'
    }
  }

  const getThreadName = () => {
    if (!thread) return 'Loading...'
    if (thread.event_name) return thread.event_name
    if (thread.result_data?.name) return thread.result_data.name as string
    return `${thread.agent_type} - ${thread.thread_id.slice(-8)}`
  }

  const getDuration = () => {
    if (!thread) return null
    const start = new Date(thread.started_at)
    const end = thread.completed_at ? new Date(thread.completed_at) : new Date()
    const diff = end.getTime() - start.getTime()
    const minutes = Math.floor(diff / 60000)
    const seconds = Math.floor((diff % 60000) / 1000)
    if (minutes > 0) return `${minutes}m ${seconds}s`
    return `${seconds}s`
  }

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-w-4xl h-[85vh] flex flex-col p-0">
        {/* Header */}
        <DialogHeader className="px-6 pt-6 pb-4 border-b flex flex-row items-center justify-between space-y-0">
          <div className="flex items-center gap-3 min-w-0">
            <DialogTitle className="text-lg font-semibold truncate">
              {getThreadName()}
            </DialogTitle>
            {thread && (
              <Badge variant="outline" className="capitalize flex-shrink-0">
                {thread.agent_type}
              </Badge>
            )}
            {isConnected ? (
              <Wifi className="h-4 w-4 text-green-500 flex-shrink-0" />
            ) : (
              <WifiOff className="h-4 w-4 text-muted-foreground flex-shrink-0" />
            )}
          </div>
          <Button variant="ghost" size="icon" onClick={onClose} className="flex-shrink-0">
            <X className="h-4 w-4" />
          </Button>
        </DialogHeader>

        {/* Thread Stats Bar */}
        {thread && (
          <div className="px-6 py-3 border-b bg-muted/30">
            <div className="flex items-center gap-6 text-sm">
              <div className="flex items-center gap-2">
                <Clock className="h-4 w-4 text-muted-foreground" />
                <span className="text-muted-foreground">Duration:</span>
                <span className="font-medium">{getDuration()}</span>
              </div>
              {thread.total_tokens > 0 && (
                <div className="flex items-center gap-2">
                  <BarChart3 className="h-4 w-4 text-muted-foreground" />
                  <span className="text-muted-foreground">Tokens:</span>
                  <span className="font-medium">{thread.total_tokens.toLocaleString()}</span>
                </div>
              )}
              {thread.cost_cents > 0 && (
                <div className="flex items-center gap-2">
                  <DollarSign className="h-4 w-4 text-muted-foreground" />
                  <span className="text-muted-foreground">Cost:</span>
                  <span className="font-medium">{formatCurrency(thread.cost_cents)}</span>
                </div>
              )}
              <div className="flex items-center gap-2">
                <span className="text-muted-foreground">Status:</span>
                <Badge
                  variant="outline"
                  className={cn(
                    'capitalize',
                    thread.status === 'running' && 'border-green-500 text-green-600 bg-green-50 dark:bg-green-950/20',
                    thread.status === 'completed' && 'border-muted-foreground',
                    thread.status === 'failed' && 'border-destructive text-destructive bg-destructive/5'
                  )}
                >
                  {thread.status}
                </Badge>
              </div>
              {thread.festival_id && (
                <Link href={`/festivals/${thread.festival_id}`} className="ml-auto">
                  <Button variant="ghost" size="sm" className="gap-1">
                    View Festival
                    <ExternalLink className="h-3 w-3" />
                  </Button>
                </Link>
              )}
            </div>
          </div>
        )}

        {/* Events Stream */}
        <div className="flex-1 min-h-0 overflow-hidden">
          <ScrollArea className="h-full" ref={scrollRef}>
            <div className="p-6 space-y-4">
              {isLoading && events.length === 0 && (
                <div className="flex flex-col items-center justify-center py-16 gap-4">
                  <Loader2 className="h-10 w-10 animate-spin text-muted-foreground" />
                  <p className="text-muted-foreground">Loading thread events...</p>
                </div>
              )}

              {events.length === 0 && !isLoading && (
                <div className="text-center py-16 text-muted-foreground">
                  <Bot className="h-16 w-16 mx-auto mb-4 opacity-20" />
                  <p className="text-lg font-medium">No events yet</p>
                  <p className="text-sm">This thread hasn't produced any events.</p>
                </div>
              )}

              {events.map((event, index) => (
                <div
                  key={event.id}
                  className={cn(
                    'rounded-lg border p-4 transition-all animate-in fade-in slide-in-from-bottom-2 duration-300',
                    getEventColor(event.type)
                  )}
                  style={{
                    animationDelay: `${Math.min(index * 30, 300)}ms`,
                  }}
                >
                  <div className="flex items-start gap-3">
                    <div className="mt-0.5 flex-shrink-0">{getEventIcon(event.type)}</div>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center justify-between mb-2">
                        <span className="text-xs font-medium capitalize opacity-70">
                          {event.type}
                        </span>
                        <span className="text-xs opacity-50">
                          {new Date(event.timestamp).toLocaleTimeString()}
                        </span>
                      </div>
                      <EventContent event={event} />
                    </div>
                  </div>
                </div>
              ))}

              {isConnected && (
                <div className="flex items-center justify-center gap-2 py-6 text-sm text-muted-foreground">
                  <Loader2 className="h-4 w-4 animate-spin" />
                  <span>Listening for new events...</span>
                </div>
              )}
            </div>
          </ScrollArea>
        </div>

        {/* Footer */}
        {thread && (
          <div className="px-6 py-3 border-t bg-muted/30 flex items-center justify-between text-xs text-muted-foreground">
            <div className="flex items-center gap-4">
              <span>Started {formatRelativeTime(thread.started_at)}</span>
              {events.length > 0 && (
                <span>{events.length} events</span>
              )}
            </div>
            {thread.festival_id && (
              <Link href={`/festivals/${thread.festival_id}`}>
                <Button variant="ghost" size="sm" className="gap-1 h-7 text-xs">
                  Open Festival Page
                  <ExternalLink className="h-3 w-3" />
                </Button>
              </Link>
            )}
          </div>
        )}
      </DialogContent>
    </Dialog>
  )
}

function EventContent({ event }: { event: StreamEvent }) {
  if (event.type === 'message') {
    const content = event.content as { content?: string; role?: string }
    return (
      <div className="space-y-1">
        {content.role && (
          <span className="text-xs font-medium capitalize opacity-70">
            {content.role}
          </span>
        )}
        {content.content && (
          <p className="text-sm whitespace-pre-wrap leading-relaxed">{content.content}</p>
        )}
      </div>
    )
  }

  if (event.type === 'tool') {
    const content = event.content as { name?: string; input?: unknown; output?: unknown; state?: string }
    return (
      <div className="space-y-2">
        <div className="flex items-center gap-2">
          {content.name && (
            <Badge variant="secondary" className="text-xs">
              {content.name}
            </Badge>
          )}
          {content.state && (
            <span className="text-xs opacity-70 capitalize">{content.state}</span>
          )}
        </div>
        {!!content.input && (
          <div className="text-xs opacity-70">
            <span className="font-medium">Input:</span>{' '}
            {typeof content.input === 'string' 
              ? content.input 
              : JSON.stringify(content.input, null, 2)}
          </div>
        )}
        {!!content.output && (
          <div className="text-xs">
            <span className="font-medium">Output:</span>{' '}
            {typeof content.output === 'string'
              ? content.output
              : JSON.stringify(content.output, null, 2)}
          </div>
        )}
      </div>
    )
  }

  if (event.type === 'reasoning') {
    const content = event.content as { data?: { step?: string; thought?: string; evaluation?: string } }
    return (
      <div className="space-y-2">
        {content.data?.step && (
          <Badge variant="outline" className="text-xs capitalize">
            {content.data.step}
          </Badge>
        )}
        {content.data?.thought && (
          <p className="text-sm opacity-90 leading-relaxed">{content.data.thought}</p>
        )}
        {content.data?.evaluation && (
          <div className="text-xs opacity-70 mt-1 pt-2 border-t border-current/20">
            <span className="font-medium">Evaluation:</span> {content.data.evaluation}
          </div>
        )}
      </div>
    )
  }

  if (event.type === 'error') {
    const content = event.content as { error?: string }
    return (
      <p className="text-sm font-medium">{content.error || 'Unknown error'}</p>
    )
  }

  // Default: show JSON
  return (
    <pre className="text-xs overflow-auto max-h-40 whitespace-pre-wrap">
      {JSON.stringify(event.content, null, 2)}
    </pre>
  )
}

function convertEventType(eventType: string): StreamEvent['type'] {
  switch (eventType) {
    case 'messages':
      return 'message'
    case 'tools':
      return 'tool'
    case 'custom':
      return 'custom'
    case 'error':
      return 'error'
    default:
      return 'custom'
  }
}
