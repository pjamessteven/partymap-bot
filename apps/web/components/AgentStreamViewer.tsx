"use client";

import { useCallback, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Loader2, Play, CheckCircle, XCircle, Copy, Check } from "lucide-react";
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
import { useAgentStream } from "@/lib/hooks/use-agent-stream";
import { RichToolOutput } from "@/components/agents/RichToolOutput";
import { Shimmer } from "@/components/ai-elements/shimmer";

interface AgentStreamViewerProps {
  festivalId: string;
  threadId?: string;
  onComplete?: () => void;
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
      {copied ? (
        <Check className="h-3.5 w-3.5" />
      ) : (
        <Copy className="h-3.5 w-3.5" />
      )}
    </MessageAction>
  );
}

export function AgentStreamViewer({
  festivalId,
  threadId: initialThreadId,
  onComplete,
}: AgentStreamViewerProps) {
  const [threadId, setThreadId] = useState<string | undefined>(initialThreadId);
  const { stream, customEvents } = useAgentStream(threadId ?? null);

  const startStream = useCallback(async () => {
    try {
      const response = await fetch(
        `/api/agents/${festivalId}/research/start`,
        { method: "POST" }
      );
      const data = await response.json();
      setThreadId(data.thread_id);
    } catch (e) {
      console.error("Failed to start research:", e);
    }
  }, [festivalId]);

  const isRunning = stream.isLoading;
  const isComplete =
    !stream.isLoading &&
    stream.messages.length > 0 &&
    !stream.error;
  const hasError = !!stream.error;

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
        <div className="flex flex-wrap items-center gap-2 sm:gap-3">
          <h3 className="text-base sm:text-lg font-semibold">Research Agent</h3>
          {isRunning && (
            <Badge variant="default" className="animate-pulse bg-green-500 text-xs">
              <Loader2 className="h-3 w-3 mr-1 animate-spin" />
              Running
            </Badge>
          )}
          {isComplete && !hasError && (
            <Badge variant="secondary" className="bg-green-100 text-green-800 text-xs">
              <CheckCircle className="h-3 w-3 mr-1" />
              Complete
            </Badge>
          )}
          {hasError && (
            <Badge variant="destructive" className="text-xs">
              <XCircle className="h-3 w-3 mr-1" />
              Error
            </Badge>
          )}
        </div>

        {!isRunning && !isComplete && (
          <Button onClick={startStream} size="sm" className="w-full sm:w-auto">
            <Play className="h-4 w-4 mr-2" />
            Start Research
          </Button>
        )}
      </div>

      {/* Stream content */}
      {threadId ? (
        <Card>
          <CardContent className="p-0">
            <div className="h-[50vh] sm:h-[500px]">
              <Conversation>
                <ConversationContent className="p-4">
                  {stream.messages.length === 0 && !isRunning && (
                    <div className="flex h-full items-center justify-center text-muted-foreground">
                      Waiting for agent to start...
                    </div>
                  )}

                  {stream.messages.map((msg, i) => {
                    if (HumanMessage.isInstance(msg)) {
                      return (
                        <Message key={msg.id ?? i} from="user">
                          <MessageContent>
                            {msg.content as string}
                          </MessageContent>
                        </Message>
                      );
                    }

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
                          {toolCalls.map((tc) => (
                            <Tool
                              key={tc.call.id}
                              defaultOpen={
                                tc.call.state !== "output-available"
                              }
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

                  {/* Reasoning */}
                  {customEvents
                    .filter((e) => e.type === "reasoning")
                    .map((evt) => {
                      const data = evt.data as {
                        thought?: string;
                        iteration?: number;
                      };
                      return (
                        <Reasoning key={evt.id}>
                          <ReasoningTrigger />
                          <ReasoningContent>
                            {[
                              data.iteration
                                ? `**Iteration ${data.iteration}**`
                                : "",
                              data.thought || "",
                            ]
                              .filter(Boolean)
                              .join("\n\n")}
                          </ReasoningContent>
                        </Reasoning>
                      );
                    })}

                  {/* Evaluation */}
                  {customEvents
                    .filter((e) => e.type === "evaluation")
                    .map((evt) => {
                      const data = evt.data as {
                        has_minimum_required?: boolean;
                        missing_fields?: string[];
                      };
                      return (
                        <div
                          key={evt.id}
                          className={`rounded-md border p-3 text-sm ${
                            data.has_minimum_required
                              ? "border-green-200 bg-green-50 dark:border-green-900 dark:bg-green-950"
                              : "border-yellow-200 bg-yellow-50 dark:border-yellow-900 dark:bg-yellow-950"
                          }`}
                        >
                          <div className="font-medium">
                            {data.has_minimum_required
                              ? "✓ Requirements met"
                              : "⏳ Collecting more data..."}
                          </div>
                          {data.missing_fields &&
                            data.missing_fields.length > 0 && (
                              <div className="mt-1 text-muted-foreground">
                                Missing:{" "}
                                {data.missing_fields.join(", ")}
                              </div>
                            )}
                        </div>
                      );
                    })}

                  {isRunning &&
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
          </CardContent>
        </Card>
      ) : (
        <Card>
          <CardContent className="py-12 text-center text-muted-foreground">
            Click "Start Research" to begin researching this festival
          </CardContent>
        </Card>
      )}

      {threadId && (
        <div className="text-xs text-muted-foreground">
          Thread: <code className="bg-muted px-1 rounded">{threadId}</code>
        </div>
      )}
    </div>
  );
}
