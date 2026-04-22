'use client'

import { useQuery } from '@tanstack/react-query'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Play, Check, X, Clock, Loader2 } from 'lucide-react'
import { cn } from '@/lib/utils'
import { formatDistanceToNow } from 'date-fns'

interface Thread {
  thread_id: string
  agent_type: string
  status: 'running' | 'completed' | 'failed'
  festival_id?: string
  event_name?: string
  started_at: string
  completed_at?: string
  total_tokens: number
  cost_cents: number
  result_data?: Record<string, unknown>
}

interface ThreadListProps {
  agentType: 'research' | 'discovery'
  selectedThread: string | null
  onSelectThread: (threadId: string) => void
}

async function getThreads(agentType: string): Promise<{ threads: Thread[] }> {
  const response = await fetch(`/api/threads?agent_type=${agentType}&limit=50`)
  if (!response.ok) throw new Error('Failed to fetch threads')
  return response.json()
}

export function ThreadList({ agentType, selectedThread, onSelectThread }: ThreadListProps) {
  const { data, isLoading, error } = useQuery({
    queryKey: ['threads', agentType],
    queryFn: () => getThreads(agentType),
    refetchInterval: 3000, // Poll every 3 seconds
  })

  const threads = data?.threads || []
  const runningThreads = threads.filter((t) => t.status === 'running')
  const completedThreads = threads.filter((t) => t.status === 'completed')
  const failedThreads = threads.filter((t) => t.status === 'failed')

  if (isLoading) {
    return (
      <Card>
        <CardContent className="flex items-center justify-center py-8">
          <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
        </CardContent>
      </Card>
    )
  }

  if (error) {
    return (
      <Card>
        <CardContent className="py-4 text-sm text-destructive">
          Failed to load threads
        </CardContent>
      </Card>
    )
  }

  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="flex items-center justify-between text-sm font-medium">
          <span>Active Threads</span>
          {runningThreads.length > 0 && (
            <Badge variant="default" className="bg-green-500">
              {runningThreads.length} running
            </Badge>
          )}
        </CardTitle>
      </CardHeader>
      <CardContent className="p-0">
        <ScrollArea className="h-[300px]">
          <div className="space-y-1 p-4">
            {threads.length === 0 && (
              <div className="py-8 text-center text-sm text-muted-foreground">
                No threads yet
              </div>
            )}

            {/* Running threads first */}
            {runningThreads.map((thread) => (
              <ThreadItem
                key={thread.thread_id}
                thread={thread}
                isSelected={selectedThread === thread.thread_id}
                onClick={() => onSelectThread(thread.thread_id)}
              />
            ))}

            {/* Completed threads */}
            {completedThreads.slice(0, 10).map((thread) => (
              <ThreadItem
                key={thread.thread_id}
                thread={thread}
                isSelected={selectedThread === thread.thread_id}
                onClick={() => onSelectThread(thread.thread_id)}
              />
            ))}

            {/* Failed threads */}
            {failedThreads.slice(0, 5).map((thread) => (
              <ThreadItem
                key={thread.thread_id}
                thread={thread}
                isSelected={selectedThread === thread.thread_id}
                onClick={() => onSelectThread(thread.thread_id)}
              />
            ))}
          </div>
        </ScrollArea>
      </CardContent>
    </Card>
  )
}

interface ThreadItemProps {
  thread: Thread
  isSelected: boolean
  onClick: () => void
}

function ThreadItem({ thread, isSelected, onClick }: ThreadItemProps) {
  const getIcon = () => {
    switch (thread.status) {
      case 'running':
        return <Play className="h-4 w-4 text-green-500" />
      case 'completed':
        return <Check className="h-4 w-4 text-muted-foreground" />
      case 'failed':
        return <X className="h-4 w-4 text-destructive" />
      default:
        return <Clock className="h-4 w-4 text-muted-foreground" />
    }
  }

  const getName = () => {
    if (thread.event_name) return thread.event_name
    if (thread.result_data?.name) return thread.result_data.name as string
    return `${thread.agent_type} - ${thread.thread_id.slice(-8)}`
  }

  return (
    <button
      onClick={onClick}
      className={cn(
        'w-full rounded-lg border p-3 text-left transition-colors',
        isSelected
          ? 'border-primary bg-primary/5'
          : 'border-border hover:border-primary/50'
      )}
    >
      <div className="flex items-center gap-2">
        {thread.status === 'running' ? (
          <Loader2 className="h-4 w-4 animate-spin text-green-500" />
        ) : (
          getIcon()
        )}
        <span className="truncate font-medium">{getName()}</span>
      </div>
      <div className="mt-1 flex items-center justify-between text-xs text-muted-foreground">
        <span>{formatDistanceToNow(new Date(thread.started_at))} ago</span>
        {thread.total_tokens > 0 && <span>{thread.total_tokens} tokens</span>}
      </div>
    </button>
  )
}
