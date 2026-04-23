"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Alert, AlertDescription } from "@/components/ui/alert";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  getRefreshApprovals,
  approveRefresh,
  rejectRefresh,
  triggerRefresh,
} from "@/lib/api";
import type { RefreshApproval } from "@/lib/api";
import {
  CheckCircle,
  XCircle,
  RefreshCw,
  Clock,
  AlertTriangle,
} from "lucide-react";
import { formatRelativeTime, cn } from "@/lib/utils";
import { useToast } from "@/components/ui/toast-provider";
import { EmptyState } from "@/components/empty-state";
import { SkeletonCard } from "@/components/ui/skeleton";

export default function RefreshPage() {
  const queryClient = useQueryClient();
  const [selectedApproval, setSelectedApproval] =
    useState<RefreshApproval | null>(null);
  const [filter, setFilter] = useState<string>("pending");
  const { success, error } = useToast();

  const { data, isLoading, refetch } = useQuery({
    queryKey: ["refresh-approvals", filter],
    queryFn: () => getRefreshApprovals(filter === "all" ? undefined : filter),
  });

  const approveMutation = useMutation({
    mutationFn: approveRefresh,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["refresh-approvals"] });
      setSelectedApproval(null);
      success("Approval accepted");
    },
  });

  const rejectMutation = useMutation({
    mutationFn: ({ id, reason }: { id: string; reason?: string }) =>
      rejectRefresh(id, reason),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["refresh-approvals"] });
      setSelectedApproval(null);
      success("Approval rejected");
    },
  });

  const triggerMutation = useMutation({
    mutationFn: triggerRefresh,
    onSuccess: () => {
      setTimeout(() => refetch(), 2000);
      success("Refresh triggered");
    },
  });

  const getStatusBadge = (status: string) => {
    const styles: Record<string, string> = {
      pending: "bg-yellow-100 text-yellow-800",
      auto_approved: "bg-blue-100 text-blue-800",
      approved: "bg-green-100 text-green-800",
      rejected: "bg-red-100 text-red-800",
      applied: "bg-gray-100 text-gray-800",
    };
    return (
      <Badge className={styles[status] || styles.pending}>
        {status.replace("_", " ")}
      </Badge>
    );
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl sm:text-3xl font-bold">Refresh Pipeline</h1>
        <Button
          onClick={() => triggerMutation.mutate()}
          disabled={triggerMutation.isPending}
          size="sm"
        >
          <RefreshCw
            className={cn(
              "h-4 w-4 mr-2",
              triggerMutation.isPending && "animate-spin",
            )}
          />
          Trigger Refresh
        </Button>
      </div>

      <Alert>
        <Clock className="h-4 w-4" />
        <AlertDescription>
          The refresh pipeline runs weekly to verify unconfirmed dates within
          120 days. Events still unconfirmed 30 days out are automatically
          cancelled.
        </AlertDescription>
      </Alert>

      {/* Filter */}
      <div className="flex gap-2">
        {["pending", "auto_approved", "approved", "all"].map((f) => (
          <Button
            key={f}
            variant={filter === f ? "default" : "outline"}
            size="sm"
            onClick={() => setFilter(f)}
          >
            {f.replace("_", " ")}
          </Button>
        ))}
      </div>

      {/* Approvals List */}
      <div className="space-y-4">
        {isLoading ? (
          <div className="space-y-4">
            <SkeletonCard className="h-24" />
            <SkeletonCard className="h-24" />
            <SkeletonCard className="h-24" />
          </div>
        ) : data?.items.length === 0 ? (
          <EmptyState
            icon={RefreshCw}
            title="No refresh approvals"
            description="Refresh pipeline approvals will appear here when events need verification."
          />
        ) : (
          data?.items.map((approval) => (
            <Card
              key={approval.id}
              className="cursor-pointer hover:border-primary transition-colors"
              onClick={() => setSelectedApproval(approval)}
            >
              <CardContent className="pt-6">
                <div className="flex items-start justify-between">
                  <div className="space-y-2">
                    <div className="flex items-center gap-3">
                      <h3 className="font-semibold">{approval.event_name}</h3>
                      {getStatusBadge(approval.status)}
                    </div>

                    <div className="text-sm text-muted-foreground">
                      Confidence:{" "}
                      {(approval.research_confidence * 100).toFixed(0)}%{" • "}
                      {formatRelativeTime(approval.created_at)}
                    </div>

                    {approval.change_summary.length > 0 && (
                      <div className="flex flex-wrap gap-2 mt-2">
                        {approval.change_summary.map((change, i) => (
                          <Badge key={i} variant="outline" className="text-xs">
                            {change}
                          </Badge>
                        ))}
                      </div>
                    )}
                  </div>

                  {(approval.status === "pending" ||
                    approval.status === "auto_approved") && (
                    <div className="flex gap-2">
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={(e) => {
                          e.stopPropagation();
                          approveMutation.mutate(approval.id);
                        }}
                        disabled={approveMutation.isPending}
                      >
                        <CheckCircle className="h-4 w-4 mr-1" />
                        Approve
                      </Button>
                      <Button
                        size="sm"
                        variant="destructive"
                        onClick={(e) => {
                          e.stopPropagation();
                          rejectMutation.mutate({ id: approval.id });
                        }}
                        disabled={rejectMutation.isPending}
                      >
                        <XCircle className="h-4 w-4 mr-1" />
                        Reject
                      </Button>
                    </div>
                  )}
                </div>
              </CardContent>
            </Card>
          ))
        )}
      </div>

      {/* Detail Dialog */}
      <Dialog
        open={!!selectedApproval}
        onOpenChange={() => setSelectedApproval(null)}
      >
        <DialogContent className="max-w-2xl max-h-[80vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>{selectedApproval?.event_name}</DialogTitle>
            <DialogDescription>
              Review proposed changes before applying
            </DialogDescription>
          </DialogHeader>

          {selectedApproval && (
            <div className="space-y-4">
              <div className="flex items-center gap-2">
                <span className="text-sm text-muted-foreground">Status:</span>
                {getStatusBadge(selectedApproval.status)}
              </div>

              <div>
                <h4 className="font-medium mb-2">Proposed Changes:</h4>
                <ul className="space-y-1">
                  {selectedApproval.change_summary.map((change, i) => (
                    <li key={i} className="text-sm flex items-center gap-2">
                      <CheckCircle className="h-4 w-4 text-green-500" />
                      {change}
                    </li>
                  ))}
                </ul>
              </div>

              {selectedApproval.proposed_changes.event_date && (
                <div>
                  <h4 className="font-medium mb-2">EventDate Changes:</h4>
                  <pre className="bg-gray-100 p-3 rounded text-xs overflow-x-auto">
                    {JSON.stringify(
                      selectedApproval.proposed_changes.event_date,
                      null,
                      2,
                    )}
                  </pre>
                </div>
              )}

              {(selectedApproval.status === "pending" ||
                selectedApproval.status === "auto_approved") && (
                <DialogFooter className="gap-2">
                  <Button
                    variant="outline"
                    onClick={() => setSelectedApproval(null)}
                  >
                    Cancel
                  </Button>
                  <Button
                    variant="destructive"
                    onClick={() =>
                      rejectMutation.mutate({ id: selectedApproval.id })
                    }
                    disabled={rejectMutation.isPending}
                  >
                    <XCircle className="h-4 w-4 mr-2" />
                    Reject
                  </Button>
                  <Button
                    onClick={() => approveMutation.mutate(selectedApproval.id)}
                    disabled={approveMutation.isPending}
                  >
                    <CheckCircle className="h-4 w-4 mr-2" />
                    Approve & Apply
                  </Button>
                </DialogFooter>
              )}
            </div>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}


