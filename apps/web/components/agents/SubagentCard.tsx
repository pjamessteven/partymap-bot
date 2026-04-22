"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import { Bot, Loader2, CheckCircle, XCircle } from "lucide-react";

interface SubagentCardProps {
  id: string;
  name: string;
  status: "pending" | "running" | "complete" | "error";
  messages?: { role: string; content: string }[];
  progress?: number;
}

export function SubagentCard({
  id,
  name,
  status,
  messages = [],
  progress,
}: SubagentCardProps) {
  const statusConfig = {
    pending: {
      icon: <Bot className="h-4 w-4 text-muted-foreground" />,
      badge: "secondary",
      label: "Pending",
    },
    running: {
      icon: <Loader2 className="h-4 w-4 text-blue-500 animate-spin" />,
      badge: "default",
      label: "Running",
    },
    complete: {
      icon: <CheckCircle className="h-4 w-4 text-green-500" />,
      badge: "default",
      label: "Complete",
    },
    error: {
      icon: <XCircle className="h-4 w-4 text-red-500" />,
      badge: "destructive",
      label: "Error",
    },
  };

  const config = statusConfig[status];

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-sm flex items-center justify-between">
          <div className="flex items-center gap-2">
            {config.icon}
            <span>{name}</span>
            <span className="text-xs text-muted-foreground font-normal">
              {id.slice(0, 8)}...
            </span>
          </div>
          <Badge variant={config.badge as any} className="text-xs">
            {config.label}
          </Badge>
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        {status === "running" && progress !== undefined && (
          <Progress value={progress * 100} className="h-1" />
        )}
        {messages.length > 0 && (
          <div className="space-y-1.5 max-h-32 overflow-y-auto">
            {messages.slice(-3).map((msg, i) => (
              <div
                key={i}
                className={`text-xs rounded-md px-2 py-1 ${
                  msg.role === "user"
                    ? "bg-secondary ml-4"
                    : "bg-muted/50 mr-4"
                }`}
              >
                <span className="font-medium text-muted-foreground">
                  {msg.role}:
                </span>{" "}
                {msg.content.slice(0, 120)}
                {msg.content.length > 120 && "..."}
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
