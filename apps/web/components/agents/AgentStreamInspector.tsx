"use client";

import { useMemo, useState } from "react";
import {
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from "@/components/ui/tabs";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import {
  Terminal,
  Wrench,
  Brain,
  Loader2,
  CheckCircle,
  Clock,
  AlertCircle,
  Wifi,
  WifiOff,
  RefreshCw,
  Bot,
} from "lucide-react";
import { SubagentCard } from "./SubagentCard";
import {
  Conversation,
  ConversationContent,
  ConversationScrollButton,
} from "@/components/ai-elements/conversation";
import {
  Message,
  MessageContent,
  MessageResponse,
} from "@/components/ai-elements/message";
import {
  Tool,
  ToolHeader,
  ToolContent,
  ToolInput,
  ToolOutput,
} from "@/components/ai-elements/tool";
import { Reasoning, ReasoningTrigger, ReasoningContent } from "@/components/ai-elements/reasoning";
import { AIMessage, HumanMessage, ToolMessage } from "@langchain/core/messages";
import { ThinkingTimeline } from "./ThinkingTimeline";
import { RichToolOutput } from "./RichToolOutput";
import { useAgentStream, type TokenUsage } from "@/lib/hooks/use-agent-stream";
import { Zap } from "lucide-react";
import { FestivalProfileCard } from "./FestivalProfileCard";

function TokenBar({
  usage,
  status,
}: {
  usage: TokenUsage;
  status: "connected" | "disconnected" | "reconnecting";
}) {
  const statusIcon =
    status === "connected" ? (
      <Wifi className="h-3 w-3 text-green-500" />
    ) : status === "reconnecting" ? (
      <RefreshCw className="h-3 w-3 text-yellow-500 animate-spin" />
    ) : (
      <WifiOff className="h-3 w-3 text-red-500" />
    );

  return (
    <div className="flex items-center gap-2 sm:gap-3 text-xs text-muted-foreground bg-muted/50 rounded-md px-2 sm:px-3 py-1.5">
      {statusIcon}
      {usage.total_tokens > 0 && (
        <>
          <Zap className="h-3.5 w-3.5 text-yellow-500 shrink-0 hidden sm:block" />
          {/* Desktop: full breakdown */}
          <div className="hidden sm:flex flex-1 items-center gap-2">
            <div className="flex-1 h-1.5 bg-muted rounded-full overflow-hidden flex">
              <div
                className="bg-blue-500 h-full"
                style={{
                  width: `${
                    usage.total_tokens > 0
                      ? (usage.prompt_tokens / usage.total_tokens) * 100
                      : 0
                  }%`,
                }}
              />
              <div
                className="bg-green-500 h-full"
                style={{
                  width: `${
                    usage.total_tokens > 0
                      ? (usage.completion_tokens / usage.total_tokens) * 100
                      : 0
                  }%`,
                }}
              />
            </div>
          </div>
          <div className="hidden sm:flex items-center gap-3 shrink-0">
            <span>
              <span className="text-blue-600 font-medium">
                {usage.prompt_tokens.toLocaleString()}
              </span>{" "}
              prompt
            </span>
            <span>
              <span className="text-green-600 font-medium">
                {usage.completion_tokens.toLocaleString()}
              </span>{" "}
              completion
            </span>
            <span className="font-semibold text-foreground">
              {usage.total_tokens.toLocaleString()} total
            </span>
          </div>
          {/* Mobile: compact total only */}
          <span className="sm:hidden font-semibold text-foreground">
            {usage.total_tokens.toLocaleString()} tokens
          </span>
        </>
      )}
      {usage.total_tokens === 0 && (
        <span className="capitalize">{status}</span>
      )}
    </div>
  );
}

interface AgentStreamInspectorProps {
  threadId: string | null;
}

export function AgentStreamInspector({ threadId }: AgentStreamInspectorProps) {
  const [connectionStatus, setConnectionStatus] = useState<
    "connected" | "disconnected" | "reconnecting"
  >("connected");

  const { stream, customEvents, tokenUsage } = useAgentStream(
    threadId,
    setConnectionStatus
  );

  const reasoningSteps = useMemo(
    () =>
      customEvents
        .filter((e) => e.type === "reasoning")
        .map((e) => ({
          id: e.id,
          thought: (e.data as { thought?: string }).thought || "",
          iteration: (e.data as { iteration?: number }).iteration,
        })),
    [customEvents]
  );

  const toolProgressEvents = useMemo(
    () =>
      customEvents
        .filter((e) => e.type === "tool_progress")
        .map((e) => ({
          id: e.id,
          toolName: (e.data as { tool_name?: string }).tool_name || "unknown",
          progress: (e.data as { progress?: number }).progress || 0,
          message: (e.data as { message?: string }).message || "",
        })),
    [customEvents]
  );

  const evaluationEvents = useMemo(
    () =>
      customEvents.filter((e) => e.type === "evaluation").map((e) => ({
        id: e.id,
        data: e.data as {
          has_minimum_required?: boolean;
          missing_fields?: string[];
        },
      })),
    [customEvents]
  );

  const subagents = useMemo(() => {
    const saList = (stream as any).subagents;
    if (!saList) return [];
    return Array.from(saList.values()).map((sa: any) => ({
      id: sa.id,
      name: sa.name || "Subagent",
      status: sa.status || "pending",
      messages: sa.messages || [],
    }));
  }, [stream]);

  if (!threadId) {
    return (
      <div className="flex h-full items-center justify-center text-muted-foreground">
        Select a thread to inspect
      </div>
    );
  }

  return (
    <Tabs defaultValue="stream" className="h-full flex flex-col">
      <TabsList
        className={`grid w-full shrink-0 ${
          subagents.length > 0 ? "grid-cols-4" : "grid-cols-3"
        }`}
      >
        <TabsTrigger value="stream" className="px-1 sm:px-3">
          <Terminal className="h-4 w-4 sm:mr-2" />
          <span className="hidden sm:inline">Stream</span>
        </TabsTrigger>
        <TabsTrigger value="tools" className="px-1 sm:px-3">
          <Wrench className="h-4 w-4 sm:mr-2" />
          <span className="hidden sm:inline">
            Tools ({(stream as any).toolCalls?.length || 0})
          </span>
        </TabsTrigger>
        <TabsTrigger value="reasoning" className="px-1 sm:px-3">
          <Brain className="h-4 w-4 sm:mr-2" />
          <span className="hidden sm:inline">
            Reasoning ({reasoningSteps.length})
          </span>
        </TabsTrigger>
        {subagents.length > 0 && (
          <TabsTrigger value="subagents" className="px-1 sm:px-3">
            <Bot className="h-4 w-4 sm:mr-2" />
            <span className="hidden sm:inline">
              Subagents ({subagents.length})
            </span>
          </TabsTrigger>
        )}
      </TabsList>

      <TokenBar usage={tokenUsage} status={connectionStatus} />

      <TabsContent value="stream" className="flex-1 min-h-0 mt-2">
        <div className="h-full overflow-y-auto space-y-3 p-2">
          <FestivalProfileCard events={customEvents} />

          <Conversation>
            <ConversationContent className="p-0">
              {stream.messages.length === 0 && !stream.isLoading && (
                <div className="flex h-full items-center justify-center text-muted-foreground">
                  Waiting for agent...
                </div>
              )}

              {stream.messages.map((msg, i) => {
                if (HumanMessage.isInstance(msg)) {
                  return (
                    <Message key={msg.id ?? i} from="user">
                      <MessageContent>{msg.content as string}</MessageContent>
                    </Message>
                  );
                }
                if (AIMessage.isInstance(msg)) {
                  const toolCalls = (stream as any).getToolCalls(msg) as Array<{
                    call: { id: string; name: string; args: Record<string, unknown>; state: string };
                    toolMessage?: ToolMessage;
                  }>;
                  return (
                    <div key={msg.id ?? i} className="space-y-2">
                      {toolCalls.map((tc) => (
                        <Tool key={tc.call.id} defaultOpen={tc.call.state !== "output-available"}>
                          <ToolHeader
                            type={`tool-${tc.call.name}`}
                            state={tc.call.state as any}
                            title={tc.call.name}
                          />
                          <ToolContent>
                            <ToolInput input={tc.call.args} />
                            {tc.toolMessage && (
                              <>
                                <RichToolOutput toolName={tc.call.name} output={tc.toolMessage.content} />
                                <ToolOutput output={tc.toolMessage.content as string} errorText={undefined} />
                              </>
                            )}
                          </ToolContent>
                        </Tool>
                      ))}
                      {msg.content && (
                        <Message from="assistant">
                          <MessageContent>
                            <MessageResponse>{msg.content as string}</MessageResponse>
                          </MessageContent>
                        </Message>
                      )}
                    </div>
                  );
                }
                if (ToolMessage.isInstance(msg)) {
                  return (
                    <Tool key={msg.id ?? i} defaultOpen={false}>
                      <ToolHeader type="dynamic-tool" state="output-available" toolName={msg.name || "tool"} title={msg.name || "tool"} />
                      <ToolContent>
                        <ToolOutput output={msg.content as string} errorText={undefined} />
                      </ToolContent>
                    </Tool>
                  );
                }
                return null;
              })}

              {evaluationEvents.map((evt) => (
                <div
                  key={evt.id}
                  className={`rounded-md border p-3 text-sm my-2 ${
                    evt.data.has_minimum_required
                      ? "border-green-200 bg-green-50 dark:border-green-900 dark:bg-green-950"
                      : "border-yellow-200 bg-yellow-50 dark:border-yellow-900 dark:bg-yellow-950"
                  }`}
                >
                  <div className="font-medium">
                    {evt.data.has_minimum_required ? "✓ Requirements met" : "⏳ Collecting more data..."}
                  </div>
                  {evt.data.missing_fields && evt.data.missing_fields.length > 0 && (
                    <div className="mt-1 text-muted-foreground">Missing: {evt.data.missing_fields.join(", ")}</div>
                  )}
                </div>
              ))}

              {stream.isLoading && (
                <div className="flex items-center gap-2 text-muted-foreground py-2">
                  <Loader2 className="h-4 w-4 animate-spin" />
                  Agent is working...
                </div>
              )}
            </ConversationContent>
            <ConversationScrollButton />
          </Conversation>
        </div>
      </TabsContent>

      <TabsContent value="tools" className="flex-1 min-h-0 mt-2 overflow-y-auto">
        <div className="space-y-3">
          {(stream as any).toolCalls?.length === 0 && toolProgressEvents.length === 0 && (
            <Card>
              <CardContent className="py-8 text-center text-muted-foreground">
                No tool calls yet
              </CardContent>
            </Card>
          )}

          {(stream as any).toolCalls?.map((tc: any) => {
            const progress = toolProgressEvents
              .filter((p) => p.toolName === tc.call.name)
              .pop();
            return (
              <Card key={tc.call.id}>
                <CardContent className="pt-4 space-y-3">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <Wrench className="h-4 w-4 text-muted-foreground" />
                      <span className="font-medium text-sm">{tc.call.name}</span>
                    </div>
                    <Badge
                      variant={
                        tc.call.state === "output-available"
                          ? "default"
                          : tc.call.state === "output-error"
                            ? "destructive"
                            : "secondary"
                      }
                      className="text-xs"
                    >
                      {tc.call.state === "output-available" ? (
                        <CheckCircle className="h-3 w-3 mr-1" />
                      ) : tc.call.state === "input-available" ? (
                        <Clock className="h-3 w-3 mr-1" />
                      ) : (
                        <AlertCircle className="h-3 w-3 mr-1" />
                      )}
                      {tc.call.state}
                    </Badge>
                  </div>

                  {progress && progress.progress < 1 && (
                    <div className="space-y-1">
                      <Progress value={progress.progress * 100} className="h-1.5" />
                      <p className="text-xs text-muted-foreground">{progress.message}</p>
                    </div>
                  )}

                  {tc.toolMessage && (
                    <RichToolOutput toolName={tc.call.name} output={tc.toolMessage.content} />
                  )}
                </CardContent>
              </Card>
            );
          })}
        </div>
      </TabsContent>

      <TabsContent value="reasoning" className="flex-1 min-h-0 mt-2 overflow-y-auto">
        {reasoningSteps.length === 0 ? (
          <Card>
            <CardContent className="py-8 text-center text-muted-foreground">
              No reasoning recorded yet
            </CardContent>
          </Card>
        ) : (
          <ThinkingTimeline steps={reasoningSteps} />
        )}
      </TabsContent>

      {subagents.length > 0 && (
        <TabsContent
          value="subagents"
          className="flex-1 min-h-0 mt-2 overflow-y-auto"
        >
          <div className="space-y-3">
            {subagents.map((sa) => (
              <SubagentCard
                key={sa.id}
                id={sa.id}
                name={sa.name}
                status={sa.status}
                messages={sa.messages}
              />
            ))}
          </div>
        </TabsContent>
      )}
    </Tabs>
  );
}
