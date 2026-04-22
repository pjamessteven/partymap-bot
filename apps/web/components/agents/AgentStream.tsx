'use client'

import { useAgentStream, ToolCall, CustomEvent } from '@/lib/hooks/use-agent-stream'
import {
  Conversation,
  ConversationContent,
  ConversationScrollButton,
} from '@/components/ai-elements/conversation'
import {
  Message,
  MessageContent,
  MessageResponse,
} from '@/components/ai-elements/message'
import {
  Tool,
  ToolHeader,
  ToolContent,
  ToolInput,
  ToolOutput,
} from '@/components/ai-elements/tool'
import {
  Reasoning,
  ReasoningTrigger,
  ReasoningContent,
} from '@/components/ai-elements/reasoning'
import { AIMessage, BaseMessage, HumanMessage } from '@langchain/core/messages'
import { Loader2 } from 'lucide-react'

interface AgentStreamProps {
  threadId: string | null
}

export function AgentStream({ threadId }: AgentStreamProps) {
  const { messages, isLoading } = useAgentStream({ threadId })

  if (!threadId) {
    return (
      <div className="flex h-full items-center justify-center text-muted-foreground">
        Select a thread to view agent activity
      </div>
    )
  }

  return (
    <div className="flex h-full flex-col">
      <Conversation className="flex-1">
        <ConversationContent>
          {messages.length === 0 && !isLoading && (
            <div className="flex h-full items-center justify-center text-muted-foreground">
              No messages yet. Waiting for agent to start...
            </div>
          )}

          {messages.map((msg, i) => {
            // Human message
            if (msg instanceof HumanMessage) {
              return (
                <Message key={i} from="user">
                  <MessageContent>{msg.content as string}</MessageContent>
                </Message>
              )
            }

            // AI message
            if (msg instanceof AIMessage) {
              return (
                <div key={i} className="space-y-2">
                  <Message from="assistant">
                    <MessageContent>
                      {msg.content && (
                        <MessageResponse>{msg.content as string}</MessageResponse>
                      )}
                    </MessageContent>
                  </Message>
                </div>
              )
            }

            // Tool call
            if ((msg as ToolCall).id && (msg as ToolCall).name) {
              const tool = msg as ToolCall
              return (
                <Tool key={tool.id} defaultOpen={tool.state === 'input-available'}>
                  <ToolHeader
                    type={`tool-${tool.name}`}
                    state={tool.state}
                    title={tool.name}
                  />
                  <ToolContent>
                    <ToolInput input={tool.args} />
                    {tool.output !== undefined && (
                      <ToolOutput output={tool.output} errorText={undefined} />
                    )}
                  </ToolContent>
                </Tool>
              )
            }

            // Custom event (reasoning, evaluation)
            if ((msg as CustomEvent).type === 'custom') {
              const custom = msg as CustomEvent
              if (custom.eventType === 'reasoning') {
                const data = custom.data as { thought?: string; iteration?: number }
                const reasoningContent = [
                  data.iteration ? `**Iteration ${data.iteration}**` : '',
                  data.thought || JSON.stringify(custom.data, null, 2)
                ].filter(Boolean).join('\n\n')
                return (
                  <Reasoning key={i}>
                    <ReasoningTrigger />
                    <ReasoningContent>{reasoningContent}</ReasoningContent>
                  </Reasoning>
                )
              }
              if (custom.eventType === 'evaluation') {
                const data = custom.data as {
                  has_minimum_required?: boolean
                  missing_fields?: string[]
                }
                return (
                  <div
                    key={i}
                    className={`rounded-md border p-3 text-sm ${
                      data.has_minimum_required
                        ? 'border-green-200 bg-green-50 dark:border-green-900 dark:bg-green-950'
                        : 'border-yellow-200 bg-yellow-50 dark:border-yellow-900 dark:bg-yellow-950'
                    }`}
                  >
                    <div className="font-medium">
                      {data.has_minimum_required
                        ? '✓ Requirements met'
                        : '⏳ Collecting more data...'}
                    </div>
                    {data.missing_fields && data.missing_fields.length > 0 && (
                      <div className="mt-1 text-muted-foreground">
                        Missing: {data.missing_fields.join(', ')}
                      </div>
                    )}
                  </div>
                )
              }
              // Generic custom event
              return (
                <div
                  key={i}
                  className="rounded-md border border-muted bg-muted/50 p-3 text-sm"
                >
                  <div className="font-medium capitalize">{custom.eventType}</div>
                  <pre className="mt-1 overflow-auto text-xs">
                    {JSON.stringify(custom.data, null, 2)}
                  </pre>
                </div>
              )
            }

            return null
          })}

          {isLoading && (
            <div className="flex items-center gap-2 text-muted-foreground">
              <Loader2 className="h-4 w-4 animate-spin" />
              Agent is working...
            </div>
          )}
        </ConversationContent>
        <ConversationScrollButton />
      </Conversation>
    </div>
  )
}
