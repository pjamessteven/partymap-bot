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
} from "@/components/ai-elements/message";
import {
  Tool,
  ToolHeader,
  ToolContent,
} from "@/components/ai-elements/tool";
import { Loader2, Search, Database, RefreshCw, CheckCircle, AlertCircle } from "lucide-react";
import { useAgentStream } from "@/lib/hooks/use-agent-stream";
import { Shimmer } from "@/components/ai-elements/shimmer";

interface JobStreamProps {
  threadId: string | null;
  jobType: 'discovery' | 'goabase' | 'sync' | 'research';
}

// Icons for different job types
const jobIcons = {
  discovery: Search,
  goabase: Database,
  sync: RefreshCw,
  research: Loader2,
};

// Display names for job types
const jobNames = {
  discovery: "Discovery",
  goabase: "Goabase Sync",
  sync: "PartyMap Sync",
  research: "Research",
};

export function JobStream({ threadId, jobType }: JobStreamProps) {
  const { stream, customEvents } = useAgentStream(threadId);
  const Icon = jobIcons[jobType];

  // Process events into display items
  const displayItems = useMemo(() => {
    const items: Array<{
      id: string;
      type: 'info' | 'progress' | 'festival' | 'complete' | 'error';
      content: any;
      timestamp?: string;
    }> = [];

    customEvents.forEach((evt, idx) => {
      const evtData = evt.data as Record<string, any> | undefined
      const eventType = evtData?.event
      const eventData = evtData?.data || {}

      switch (eventType) {
        case 'info':
          items.push({
            id: `info-${idx}`,
            type: 'info',
            content: eventData.message,
            timestamp: evtData?.timestamp,
          })
          break

        case 'progress':
          items.push({
            id: `progress-${idx}`,
            type: 'progress',
            content: eventData,
            timestamp: evtData?.timestamp,
          })
          break

        case 'festival':
          items.push({
            id: `festival-${idx}`,
            type: 'festival',
            content: eventData,
            timestamp: evtData?.timestamp,
          })
          break

        case 'complete':
          items.push({
            id: `complete-${idx}`,
            type: 'complete',
            content: eventData,
            timestamp: evtData?.timestamp,
          })
          break

        case 'error':
          items.push({
            id: `error-${idx}`,
            type: 'error',
            content: eventData.message || 'Unknown error',
            timestamp: evtData?.timestamp,
          })
          break

        default:
          items.push({
            id: `unknown-${idx}`,
            type: 'info',
            content: JSON.stringify(evtData),
            timestamp: evtData?.timestamp,
          })
      }
    })

    return items;
  }, [customEvents]);

  // Check if job is still running
  const isRunning = stream.isLoading || 
    (displayItems.length > 0 && displayItems[displayItems.length - 1].type !== 'complete');

  if (!threadId) {
    return (
      <div className="flex h-full items-center justify-center text-muted-foreground">
        Select a thread to view {jobNames[jobType].toLowerCase()} activity
      </div>
    );
  }

  return (
    <div className="flex h-full flex-col">
      <Conversation className="flex-1">
        <ConversationContent>
          {/* Job Header */}
          <Message from="assistant">
            <MessageContent>
              <div className="flex items-center gap-2 font-medium">
                <Icon className="h-4 w-4" />
                {jobNames[jobType]} Job Started
              </div>
            </MessageContent>
          </Message>

          {/* Event List */}
          {displayItems.map((item) => {
            switch (item.type) {
              case 'info':
                return (
                  <Message key={item.id} from="assistant" className="text-sm">
                    <MessageContent className="text-muted-foreground">
                      {item.content}
                    </MessageContent>
                  </Message>
                );

              case 'progress':
                return (
                  <Tool key={item.id} defaultOpen={true}>
                    <ToolHeader
                      type="tool-progress"
                      state="input-available"
                      title="Progress"
                    />
                    <ToolContent>
                      <div className="space-y-2">
                        <div className="flex justify-between text-sm">
                          <span>{item.content.current_party || 'Processing...'}</span>
                          <span className="text-muted-foreground">
                            {item.content.current} / {item.content.total}
                          </span>
                        </div>
                        <div className="h-2 rounded-full bg-muted">
                          <div
                            className="h-full rounded-full bg-primary transition-all"
                            style={{ width: `${item.content.percent}%` }}
                          />
                        </div>
                      </div>
                    </ToolContent>
                  </Tool>
                );

              case 'festival':
                return (
                  <Tool key={item.id} defaultOpen={false}>
                    <ToolHeader
                      type="tool-success"
                      state="output-available"
                      title={item.content.name}
                    />
                    <ToolContent>
                      <div className="space-y-1 text-sm">
                        <div className="flex items-center gap-2">
                          <span className="text-muted-foreground">Status:</span>
                          <span className={
                            item.content.status === 'new' 
                              ? 'text-green-600' 
                              : item.content.status === 'update'
                              ? 'text-blue-600'
                              : 'text-gray-600'
                          }>
                            {item.content.status === 'new' && 'New Festival'}
                            {item.content.status === 'update' && 'Update Needed'}
                            {item.content.status === 'synced' && 'Synced'}
                          </span>
                        </div>
                        {item.content.source_url && (
                          <div className="text-xs text-muted-foreground truncate">
                            {item.content.source_url}
                          </div>
                        )}
                      </div>
                    </ToolContent>
                  </Tool>
                );

              case 'complete':
                return (
                  <Message key={item.id} from="assistant">
                    <MessageContent>
                      <div className="flex items-center gap-2 text-green-600">
                        <CheckCircle className="h-4 w-4" />
                        <span className="font-medium">Job Complete</span>
                      </div>
                      <div className="mt-2 text-sm text-muted-foreground space-y-1">
                        {item.content.total_found !== undefined && (
                          <div>Found: {item.content.total_found} festivals</div>
                        )}
                        {item.content.new_count !== undefined && (
                          <div>New: {item.content.new_count} | Updates: {item.content.update_count} | Errors: {item.content.error_count}</div>
                        )}
                        {item.content.saved !== undefined && (
                          <div>Saved: {item.content.saved} festivals</div>
                        )}
                        {item.content.synced !== undefined && (
                          <div>Synced: {item.content.synced} | Failed: {item.content.failed} | Total: {item.content.total}</div>
                        )}
                      </div>
                    </MessageContent>
                  </Message>
                );

              case 'error':
                return (
                  <Message key={item.id} from="assistant">
                    <MessageContent>
                      <div className="flex items-center gap-2 text-destructive">
                        <AlertCircle className="h-4 w-4" />
                        <span>{item.content}</span>
                      </div>
                    </MessageContent>
                  </Message>
                );

              default:
                return null;
            }
          })}

          {/* Loading State */}
          {isRunning && displayItems.length === 0 && (
            <div className="space-y-2 py-4">
              <Shimmer duration={1.5}>Initializing...</Shimmer>
              <div className="h-2 w-3/4 bg-muted rounded animate-pulse" />
              <div className="h-2 w-1/2 bg-muted rounded animate-pulse" />
            </div>
          )}

          {/* Running Indicator */}
          {isRunning && displayItems.length > 0 && (
            <div className="flex items-center gap-2 py-2 text-muted-foreground">
              <Loader2 className="h-4 w-4 animate-spin" />
              <span className="text-sm">Processing...</span>
            </div>
          )}
        </ConversationContent>
        <ConversationScrollButton />
      </Conversation>
    </div>
  );
}
