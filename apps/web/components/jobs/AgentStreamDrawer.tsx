"use client";

import { useEffect, useState } from "react";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetDescription,
} from "@/components/ui/sheet";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Loader2, ExternalLink } from "lucide-react";
import Link from "next/link";
import { AgentStreamInspector } from "@/components/agents/AgentStreamInspector";

interface AgentStreamDrawerProps {
  open: boolean;
  onClose: () => void;
  festivalId: string | null;
  jobType: string | null;
}

export function AgentStreamDrawer({
  open,
  onClose,
  festivalId,
  jobType,
}: AgentStreamDrawerProps) {
  const [threadId, setThreadId] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);

  useEffect(() => {
    if (!open || !festivalId) {
      setThreadId(null);
      return;
    }

    setIsLoading(true);
    fetch(`/api/festivals/${festivalId}/streams`)
      .then((res) => res.json())
      .then((data) => {
        const items = data.items || [];
        const researchThread = items.find(
          (t: { agent_type: string }) => t.agent_type === "research"
        );
        setThreadId(researchThread?.thread_id || null);
      })
      .catch(() => setThreadId(null))
      .finally(() => setIsLoading(false));
  }, [open, festivalId]);

  const getJobTypeLabel = (type: string | null) => {
    const labels: Record<string, string> = {
      discovery: "Discovery",
      research: "Research",
      sync: "Sync",
      goabase_sync: "Goabase Sync",
    };
    return type ? labels[type] || type : "Agent";
  };

  if (!festivalId) {
    return (
      <Sheet open={open} onOpenChange={onClose}>
        <SheetContent className="w-full sm:max-w-xl">
          <SheetHeader>
            <SheetTitle>No Festival Selected</SheetTitle>
          </SheetHeader>
        </SheetContent>
      </Sheet>
    );
  }

  return (
    <Sheet open={open} onOpenChange={onClose}>
      <SheetContent className="w-full sm:max-w-2xl flex flex-col">
        <SheetHeader className="space-y-2 shrink-0">
          <div className="flex items-center justify-between">
            <SheetTitle className="flex items-center gap-2">
              {getJobTypeLabel(jobType)} Inspector
              {threadId && (
                <Badge
                  variant="default"
                  className="bg-green-500 animate-pulse"
                >
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
            Real-time agent activity with tool progress and reasoning timeline
          </SheetDescription>
        </SheetHeader>

        <div className="mt-4 flex-1 min-h-0">
          {isLoading ? (
            <div className="flex h-full items-center justify-center text-muted-foreground">
              <Loader2 className="h-5 w-5 animate-spin mr-2" />
              Loading stream...
            </div>
          ) : (
            <AgentStreamInspector threadId={threadId} />
          )}
        </div>
      </SheetContent>
    </Sheet>
  );
}
