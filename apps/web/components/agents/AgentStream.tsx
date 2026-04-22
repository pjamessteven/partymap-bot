"use client";

import { useMemo } from "react";
import {
  Conversation,
  ConversationContent,
  ConversationScrollButton,
} from "@/components/ai-elements/conversation";
import {
  Message,
  MessageContent,
  MessageResponse,
  MessageActions,
  MessageAction,
} from "@/components/ai-elements/message";
import {
  Tool,
  ToolHeader,
  ToolContent,
  ToolInput,
  ToolOutput,
} from "@/components/ai-elements/tool";
import {
  Reasoning,
  ReasoningTrigger,
  ReasoningContent,
} from "@/components/ai-elements/reasoning";
import { AIMessage, HumanMessage, ToolMessage } from "@langchain/core/messages";
import { Loader2, Copy, Check } from "lucide-react";
import { useAgentStream } from "@/lib/hooks/use-agent-stream";
import { RichToolOutput } from "./RichToolOutput";
import { Shimmer } from "@/components/ai-elements/shimmer";
import { useCallback, useState } from "react";

interface AgentStreamProps {
  threadId: string | null;
}

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  const handleCopy = useCallback(() => {
    navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }, [text]);
  return (
    <MessageAction tooltip="Copy" onClick={handleCopy}>
      {copied ? <Check className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" />}
    </MessageAction>
  );
}

export function AgentStream({ threadId }: AgentStreamProps) {
  const { stream, customEvents } = useAgentStream(threadId);

  // Group reasoning events by proximity for cleaner display
  const reasoningGroups = useMemo(() => {
    const groups: { id: string; thoughts: string[] }[] = [];
    customEvents.forEach((evt) => {
      if (evt.type === "reasoning") {
        const data = evt.data as { thought?: string; iteration?: number };
        const thought = data.thought || "";
        const lastGroup = groups[groups.length - 1];
        if (lastGroup && lastGroup.thoughts.length < 5) {
          lastGroup.thoughts.push(thought);
        } else {
          groups.push({ id: evt.id, thoughts: [thought] });
        }
      }
    });
    return groups;
  }, [customEvents]);

  const evaluationEvents = useMemo(
    () =>
      customEvents
        .filter((evt) => evt.type === "evaluation")
        .map((evt) => ({
          id: evt.id,
          data: evt.data as {
            has_minimum_required?: boolean;
            missing_fields?: string[];
          },
        })),
    [customEvents]
  );

  if (!threadId) {
    return (
      <div className="flex h-full items-center justify-center text-muted-foreground">
        Select a thread to view agent activity
      </div>
    );
  }

  return (
    <div className="flex h-full flex-col">
      <Conversation className="flex-1">
        <ConversationContent>
          {stream.messages.length === 0 && !stream.isLoading && (
            <div className="flex h-full items-center justify-center text-muted-foreground">
              No messages yet. Waiting for agent to start...
            </div>
          )}

          {stream.messages.map((msg, i) => {
            // Human message
            if (HumanMessage.isInstance(msg)) {
              return (
                <Message key={msg.id ?? i} from="user">
                  <MessageContent>{msg.content as string}</MessageContent>
                </Message>
              );
            }

            // AI message (may contain tool calls)
            if (AIMessage.isInstance(msg)) {
              // eslint-disable-next-line @typescript-eslint/no-explicit-any
              const toolCalls = (stream as any).getToolCalls(msg) as Array<{
                call: {
                  id: string;
                  name: string;
                  args: Record<string, unknown>;
                  state: string;
                };
                toolMessage?: ToolMessage;
              }>;
              return (
                <div key={msg.id ?? i} className="space-y-2">
                  {/* Inline tool calls */}
                  {toolCalls.map((tc) => (
                    <Tool
                      key={tc.call.id}
                      defaultOpen={tc.call.state !== "output-available"}
                    >
                      <ToolHeader
                        type={`tool-${tc.call.name}`}
                        state={tc.call.state as "output-available" | "input-streaming" | "input-available" | "approval-requested" | "approval-responded" | "output-error" | "output-denied"}
                        title={tc.call.name}
                      />
                      <ToolContent>
                        <ToolInput input={tc.call.args} />
                        {tc.toolMessage && (
                          <>
                            <RichToolOutput
                              toolName={tc.call.name}
                              output={tc.toolMessage.content}
                            />
                            <ToolOutput
                              output={tc.toolMessage.content as string}
                              errorText={undefined}
                            />
                          </>
                        )}
                      </ToolContent>
                    </Tool>
                  ))}

                  {/* Text response */}
                  {msg.content && (
                    <Message from="assistant">
                      <MessageContent>
                        <MessageResponse>
                          {msg.content as string}
                        </MessageResponse>
                      </MessageContent>
                      <MessageActions>
                        <CopyButton text={msg.content as string} />
                      </MessageActions>
                    </Message>
                  )}
                </div>
              );
            }

            // Tool message (standalone, not paired with AI message)
            if (ToolMessage.isInstance(msg)) {
              return (
                <Tool key={msg.id ?? i} defaultOpen={false}>
                  <ToolHeader
                    type="dynamic-tool"
                    state="output-available"
                    toolName={msg.name || "tool"}
                    title={msg.name || "tool"}
                  />
                  <ToolContent>
                    <ToolOutput
                      output={msg.content as string}
                      errorText={undefined}
                    />
                  </ToolContent>
                </Tool>
              );
            }

            return null;
          })}

          {/* Reasoning blocks */}
          {reasoningGroups.map((group) => (
            <Reasoning key={group.id}>
              <ReasoningTrigger />
              <ReasoningContent>
                {group.thoughts.join("\n\n")}
              </ReasoningContent>
            </Reasoning>
          ))}

          {/* Evaluation status */}
          {evaluationEvents.map((evalEvt) => (
            <div
              key={evalEvt.id}
              className={`rounded-md border p-3 text-sm ${
                evalEvt.data.has_minimum_required
                  ? "border-green-200 bg-green-50 dark:border-green-900 dark:bg-green-950"
                  : "border-yellow-200 bg-yellow-50 dark:border-yellow-900 dark:bg-yellow-950"
              }`}
            >
              <div className="font-medium">
                {evalEvt.data.has_minimum_required
                  ? "✓ Requirements met"
                  : "⏳ Collecting more data..."}
              </div>
              {evalEvt.data.missing_fields &&
                evalEvt.data.missing_fields.length > 0 && (
                  <div className="mt-1 text-muted-foreground">
                    Missing: {evalEvt.data.missing_fields.join(", ")}
                  </div>
                )}
            </div>
          ))}

          {/* Shimmer loading state when waiting for first assistant token */}
          {stream.isLoading &&
            (stream.messages.length === 0 ||
              HumanMessage.isInstance(
                stream.messages[stream.messages.length - 1]
              )) && (
              <div className="space-y-2">
                <Shimmer duration={1.5}>Thinking...</Shimmer>
                <div className="h-2 w-3/4 bg-muted rounded animate-pulse" />
                <div className="h-2 w-1/2 bg-muted rounded animate-pulse" />
              </div>
            )}
        </ConversationContent>
        <ConversationScrollButton />
      </Conversation>
    </div>
  );
}
