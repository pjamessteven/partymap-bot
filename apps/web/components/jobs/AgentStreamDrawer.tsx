'use client'

import { useEffect, useState, useRef } from 'react'
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetDescription,
} from '@/components/ui/sheet'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Loader2, Terminal, Brain, Wrench, X, ExternalLink } from 'lucide-react'
import Link from 'next/link'

interface StreamEvent {
  type: string
  event?: any
  data?: any
  tool_name?: string
  tool_call_id?: string
  progress?: number
  message?: string
  thought?: string
}

interface ToolCall {
  id: string
  name: string
  input?: any
  output?: any
  state: 'pending' | 'running' | 'completed' | 'error'
  progress?: number
  message?: string
}

interface AgentStreamDrawerProps {
  open: boolean
  onClose: () => void
  festivalId: string | null
  jobType: string | null
}

export function AgentStreamDrawer({ open, onClose, festivalId, jobType }: AgentStreamDrawerProps) {
  const [events, setEvents] = useState<StreamEvent[]>([])
  const [toolCalls, setToolCalls] = useState<Map<string, ToolCall>>(new Map())
  const [reasoning, setReasoning] = useState<string[]>([])
  const [isConnected, setIsConnected] = useState(false)
  const [activeTab, setActiveTab] = useState('stream')
  const wsRef = useRef<WebSocket | null>(null)

  // Determine the thread ID based on job type and festival
  const getThreadId = () => {
    if (!festivalId) return null
    // Try to get the current thread from the festival
    return null // Will be fetched from API
  }

  // Connect to WebSocket when drawer opens
  useEffect(() => {
    if (!open || !festivalId) return

    // For now, we'll use the existing agent WebSocket endpoint
    // In the future, this should be enhanced to support job-specific streams
    const wsUrl = `${process.env.NEXT_PUBLIC_WS_URL || 'ws://localhost:8000'}/api/agents/${festivalId}/ws`
    const ws = new WebSocket(wsUrl)
    wsRef.current = ws

    ws.onopen = () => {
      setIsConnected(true)
    }

    ws.onmessage = (event) => {
      const data: StreamEvent = JSON.parse(event.data)
      setEvents((prev) => [...prev, data])

      // Handle different event types
      switch (data.type) {
        case 'stream_event':
          handleStreamEvent(data.event)
          break
        case 'tool_progress':
          handleToolProgress(data)
          break
        case 'reasoning':
          if (data.thought) {
            setReasoning((prev) => [...prev, data.thought as string])
          }
          break
      }
    }

    ws.onclose = () => {
      setIsConnected(false)
    }

    ws.onerror = () => {
      setIsConnected(false)
    }

    return () => {
      ws.close()
    }
  }, [open, festivalId])

  const handleStreamEvent = (event: any) => {
    if (!event) return
    const [mode, data] = event

    if (mode === 'tools' && data) {
      const toolData = data.event_data || {}
      if (toolData.event === 'on_tool_start') {
        setToolCalls((prev) => {
          const next = new Map(prev)
          next.set(data.tool_call_id, {
            id: data.tool_call_id,
            name: data.tool_name || toolData.name,
            input: toolData.input,
            state: 'running',
            progress: 0,
          })
          return next
        })
      } else if (toolData.event === 'on_tool_end') {
        setToolCalls((prev) => {
          const next = new Map(prev)
          const existing = next.get(data.tool_call_id)
          if (existing) {
            next.set(data.tool_call_id, {
              ...existing,
              output: toolData.output,
              state: 'completed',
              progress: 1,
            })
          }
          return next
        })
      }
    }
  }

  const handleToolProgress = (data: StreamEvent) => {
    const toolCallId = data.tool_call_id
    if (!toolCallId) return

    setToolCalls((prev) => {
      const next = new Map(prev)
      const existing = next.get(toolCallId)
      if (existing) {
        next.set(toolCallId, {
          ...existing,
          progress: data.progress,
          message: data.message,
          state: data.progress === 1 ? 'completed' : 'running',
        })
      } else {
        next.set(toolCallId, {
          id: toolCallId,
          name: data.tool_name || 'unknown',
          state: data.progress === 1 ? 'completed' : 'running',
          progress: data.progress,
          message: data.message,
        })
      }
      return next
    })
  }

  const getJobTypeLabel = (type: string | null) => {
    const labels: Record<string, string> = {
      discovery: 'Discovery',
      research: 'Research',
      sync: 'Sync',
      goabase_sync: 'Goabase Sync',
    }
    return type ? labels[type] || type : 'Agent'
  }

  if (!festivalId) {
    return (
      <Sheet open={open} onOpenChange={onClose}>
        <SheetContent className="w-full sm:max-w-xl">
          <SheetHeader>
            <SheetTitle>No Festival Selected</SheetTitle>
          </SheetHeader>
        </SheetContent>
      </Sheet>
    )
  }

  return (
    <Sheet open={open} onOpenChange={onClose}>
      <SheetContent className="w-full sm:max-w-2xl overflow-y-auto">
        <SheetHeader className="space-y-2">
          <div className="flex items-center justify-between">
            <SheetTitle className="flex items-center gap-2">
              {getJobTypeLabel(jobType)} Stream
              {isConnected && (
                <Badge variant="default" className="bg-green-500 animate-pulse">
                  <Loader2 className="h-3 w-3 mr-1 animate-spin" />
                  Live
                </Badge>
              )}
            </SheetTitle>
            <Link href={`/festivals/${festivalId}`}>
              <Button variant="ghost" size="sm">
                <ExternalLink className="h-4 w-4 mr-1" />
                View Festival
              </Button>
            </Link>
          </div>
          <SheetDescription>
            Real-time agent activity stream for festival processing
          </SheetDescription>
        </SheetHeader>

        <div className="mt-6">
          <Tabs value={activeTab} onValueChange={setActiveTab}>
            <TabsList className="grid w-full grid-cols-3">
              <TabsTrigger value="stream">
                <Terminal className="h-4 w-4 mr-2" />
                Stream
              </TabsTrigger>
              <TabsTrigger value="tools">
                <Wrench className="h-4 w-4 mr-2" />
                Tools ({toolCalls.size})
              </TabsTrigger>
              <TabsTrigger value="reasoning">
                <Brain className="h-4 w-4 mr-2" />
                Reasoning ({reasoning.length})
              </TabsTrigger>
            </TabsList>

            <TabsContent value="stream" className="space-y-4">
              <Card>
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm flex items-center gap-2">
                    <Terminal className="h-4 w-4" />
                    Event Log ({events.length} events)
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="bg-black text-green-400 p-3 rounded-lg font-mono text-xs max-h-96 overflow-y-auto space-y-1">
                    {events.length === 0 ? (
                      <span className="text-gray-500">
                        {isConnected ? 'Waiting for events...' : 'Connecting...'}
                      </span>
                    ) : (
                      events.map((event, i) => (
                        <div key={i} className="break-all">
                          <span className="text-gray-500">[{event.type}]</span>{' '}
                          {event.message || JSON.stringify(event.data || event.event).slice(0, 100)}
                        </div>
                      ))
                    )}
                  </div>
                </CardContent>
              </Card>
            </TabsContent>

            <TabsContent value="tools" className="space-y-4">
              {toolCalls.size === 0 ? (
                <Card>
                  <CardContent className="py-8 text-center text-muted-foreground">
                    No tool calls yet
                  </CardContent>
                </Card>
              ) : (
                Array.from(toolCalls.values()).map((tool) => (
                  <Card key={tool.id}>
                    <CardContent className="pt-4">
                      <div className="flex items-center justify-between mb-2">
                        <span className="font-medium">{tool.name}</span>
                        <Badge
                          variant={
                            tool.state === 'completed'
                              ? 'default'
                              : tool.state === 'error'
                                ? 'destructive'
                                : 'secondary'
                          }
                        >
                          {tool.state}
                        </Badge>
                      </div>

                      {tool.message && (
                        <p className="text-sm text-muted-foreground mb-2">{tool.message}</p>
                      )}

                      {tool.progress !== undefined && tool.state !== 'completed' && (
                        <div className="w-full bg-gray-200 rounded-full h-2">
                          <div
                            className="bg-blue-600 h-2 rounded-full transition-all"
                            style={{ width: `${(tool.progress || 0) * 100}%` }}
                          />
                        </div>
                      )}

                      {tool.output && (
                        <div className="mt-2 p-2 bg-gray-50 rounded text-xs font-mono overflow-x-auto">
                          {JSON.stringify(tool.output).slice(0, 200)}
                        </div>
                      )}
                    </CardContent>
                  </Card>
                ))
              )}
            </TabsContent>

            <TabsContent value="reasoning" className="space-y-4">
              {reasoning.length === 0 ? (
                <Card>
                  <CardContent className="py-8 text-center text-muted-foreground">
                    No reasoning recorded yet
                  </CardContent>
                </Card>
              ) : (
                <Card>
                  <CardContent className="pt-4">
                    <div className="space-y-3">
                      {reasoning.map((thought, i) => (
                        <div
                          key={i}
                          className="border-l-2 border-blue-300 pl-3 text-sm text-muted-foreground"
                        >
                          {thought}
                        </div>
                      ))}
                    </div>
                  </CardContent>
                </Card>
              )}
            </TabsContent>
          </Tabs>
        </div>
      </SheetContent>
    </Sheet>
  )
}
