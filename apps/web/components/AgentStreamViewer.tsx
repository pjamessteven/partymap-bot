'use client'

import { useEffect, useState, useCallback, useRef } from 'react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Loader2, Play, Square, Terminal, Brain, Wrench, CheckCircle, XCircle } from 'lucide-react'

interface StreamEvent {
  type: string
  event?: any
  data?: any
  tool_name?: string
  tool_call_id?: string
  progress?: number
  message?: string
  thought?: string
  timestamp?: string
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

interface AgentStreamViewerProps {
  festivalId: string
  threadId?: string
  onComplete?: () => void
}

export function AgentStreamViewer({ festivalId, threadId: initialThreadId, onComplete }: AgentStreamViewerProps) {
  const [threadId, setThreadId] = useState<string | undefined>(initialThreadId)
  const [isConnected, setIsConnected] = useState(false)
  const [isComplete, setIsComplete] = useState(false)
  const [events, setEvents] = useState<StreamEvent[]>([])
  const [toolCalls, setToolCalls] = useState<Map<string, ToolCall>>(new Map())
  const [reasoning, setReasoning] = useState<string[]>([])
  const [error, setError] = useState<string | null>(null)
  const wsRef = useRef<WebSocket | null>(null)

  // Start new research stream
  const startStream = useCallback(async () => {
    try {
      const response = await fetch(`/api/agents/${festivalId}/research/start`, {
        method: 'POST',
      })
      const data = await response.json()
      setThreadId(data.thread_id)
      setIsComplete(false)
      setEvents([])
      setToolCalls(new Map())
      setReasoning([])
      setError(null)
    } catch (e) {
      setError('Failed to start research: ' + (e as Error).message)
    }
  }, [festivalId])

  // Connect WebSocket when threadId changes
  useEffect(() => {
    if (!threadId) return

    const wsUrl = `${process.env.NEXT_PUBLIC_WS_URL || 'ws://localhost:8000'}/api/agents/${threadId}/ws`
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
        case 'complete':
          setIsComplete(true)
          onComplete?.()
          break
        case 'stream_error':
          setError(data.message || 'Stream error')
          break
      }
    }

    ws.onclose = () => {
      setIsConnected(false)
    }

    ws.onerror = (e) => {
      setError('WebSocket error')
      setIsConnected(false)
    }

    return () => {
      ws.close()
    }
  }, [threadId, onComplete])

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

  const stopStream = useCallback(() => {
    wsRef.current?.close()
    setIsConnected(false)
  }, [])

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <h3 className="text-lg font-semibold">Research Agent</h3>
          {isConnected && (
            <Badge variant="default" className="animate-pulse bg-green-500">
              <Loader2 className="h-3 w-3 mr-1 animate-spin" />
              Running
            </Badge>
          )}
          {isComplete && !error && (
            <Badge variant="secondary" className="bg-green-100 text-green-800">
              <CheckCircle className="h-3 w-3 mr-1" />
              Complete
            </Badge>
          )}
          {error && (
            <Badge variant="destructive">
              <XCircle className="h-3 w-3 mr-1" />
              Error
            </Badge>
          )}
        </div>

        <div className="flex gap-2">
          {!isConnected && !isComplete && (
            <Button onClick={startStream} size="sm">
              <Play className="h-4 w-4 mr-2" />
              Start Research
            </Button>
          )}
          {isConnected && (
            <Button onClick={stopStream} variant="destructive" size="sm">
              <Square className="h-4 w-4 mr-2" />
              Stop
            </Button>
          )}
        </div>
      </div>

      {/* Reasoning Section */}
      {reasoning.length > 0 && (
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm flex items-center gap-2">
              <Brain className="h-4 w-4" />
              Agent Reasoning ({reasoning.length} steps)
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-2 text-sm text-muted-foreground max-h-48 overflow-y-auto">
              {reasoning.map((thought, i) => (
                <p key={i} className="border-l-2 border-blue-300 pl-3">
                  {thought}
                </p>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Tool Calls */}
      {toolCalls.size > 0 && (
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm flex items-center gap-2">
              <Wrench className="h-4 w-4" />
              Tool Calls ({toolCalls.size})
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            {Array.from(toolCalls.values()).map((tool) => (
              <div
                key={tool.id}
                className={`border rounded-lg p-3 ${
                  tool.state === 'completed'
                    ? 'border-green-200 bg-green-50'
                    : tool.state === 'error'
                      ? 'border-red-200 bg-red-50'
                      : 'border-blue-200 bg-blue-50 animate-pulse'
                }`}
              >
                <div className="flex items-center justify-between mb-1">
                  <span className="font-medium text-sm">{tool.name}</span>
                  <Badge
                    variant={
                      tool.state === 'completed'
                        ? 'default'
                        : tool.state === 'error'
                          ? 'destructive'
                          : 'secondary'
                    }
                    className="text-xs"
                  >
                    {tool.state}
                  </Badge>
                </div>

                {tool.message && (
                  <div className="text-xs text-muted-foreground">{tool.message}</div>
                )}

                {tool.progress !== undefined && tool.state !== 'completed' && (
                  <div className="w-full bg-gray-200 rounded-full h-1.5 mt-2">
                    <div
                      className="bg-blue-600 h-1.5 rounded-full transition-all"
                      style={{ width: `${(tool.progress || 0) * 100}%` }}
                    />
                  </div>
                )}
              </div>
            ))}
          </CardContent>
        </Card>
      )}

      {/* Event Log */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm flex items-center gap-2">
            <Terminal className="h-4 w-4" />
            Event Log ({events.length} events)
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="bg-black text-green-400 p-3 rounded-lg font-mono text-xs max-h-64 overflow-y-auto space-y-1">
            {events.length === 0 ? (
              <span className="text-gray-500">
                {isConnected ? 'Waiting for events...' : 'Click "Start Research" to begin'}
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

      {/* Thread ID */}
      {threadId && (
        <div className="text-xs text-muted-foreground">
          Thread: <code className="bg-muted px-1 rounded">{threadId}</code>
        </div>
      )}
    </div>
  )
}
