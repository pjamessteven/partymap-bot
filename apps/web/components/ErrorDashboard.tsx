"use client";

import { useState } from "react";
import {
  ErrorCategory,
  CircuitBreakerMetrics,
  DLQStats,
  FestivalWithValidation,
} from "@/types";
import { ErrorCategoryBadge, RetryCountBadge } from "./ValidationBadge";

// Error Dashboard - Overview of system health
interface ErrorDashboardProps {
  dlqStats: DLQStats;
  circuitBreakers: Record<string, CircuitBreakerMetrics>;
  recentErrors: FestivalWithValidation[];
  onRetry?: (festivalId: string) => void;
  onBulkRetry?: (festivalIds: string[]) => void;
  onCleanup?: () => void;
  className?: string;
}

export function ErrorDashboard({
  dlqStats,
  circuitBreakers,
  recentErrors,
  onRetry,
  onBulkRetry,
  onCleanup,
  className = "",
}: ErrorDashboardProps) {
  const [selectedCategory, setSelectedCategory] = useState<ErrorCategory | "all">("all");

  const filteredErrors =
    selectedCategory === "all"
      ? recentErrors
      : recentErrors.filter((e) => e.error_category === selectedCategory);

  const selectedCount = filteredErrors.length;

  return (
    <div className={`space-y-6 ${className}`}>
      {/* Header */}
      <div className="flex items-center justify-between">
        <h2 className="text-xl font-semibold text-gray-900">Error Dashboard</h2>
        <div className="flex items-center gap-2">
          {onCleanup && (
            <button
              onClick={onCleanup}
              className="px-3 py-1.5 text-sm bg-gray-100 text-gray-700 rounded-md hover:bg-gray-200 transition-colors"
            >
              Cleanup Expired
            </button>
          )}
        </div>
      </div>

      {/* Stats Overview */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <DLQStatsCard stats={dlqStats} />
        <CircuitBreakerSummary breakers={circuitBreakers} />
        <ErrorTrendCard errors={recentErrors} />
      </div>

      {/* Circuit Breaker Details */}
      {Object.keys(circuitBreakers).length > 0 && (
        <div className="bg-white rounded-lg border shadow-sm p-4">
          <h3 className="font-semibold text-gray-900 mb-4">Circuit Breaker Status</h3>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {Object.entries(circuitBreakers).map(([name, metrics]) => (
              <CircuitBreakerCard key={name} name={name} metrics={metrics} />
            ))}
          </div>
        </div>
      )}

      {/* Quarantined Items */}
      <div className="bg-white rounded-lg border shadow-sm">
        <div className="px-4 py-3 border-b">
          <div className="flex items-center justify-between">
            <h3 className="font-semibold text-gray-900">
              Quarantined Festivals ({dlqStats.total_quarantined})
            </h3>
            <div className="flex items-center gap-2">
              <select
                value={selectedCategory}
                onChange={(e) => setSelectedCategory(e.target.value as ErrorCategory | "all")}
                className="text-sm border rounded-md px-2 py-1"
              >
                <option value="all">All Categories</option>
                {Object.entries(dlqStats.by_category).map(([cat, count]) => (
                  <option key={cat} value={cat}>
                    {cat} ({count})
                  </option>
                ))}
              </select>
              {onBulkRetry && selectedCount > 0 && (
                <button
                  onClick={() =>
                    onBulkRetry(filteredErrors.map((e) => e.id))
                  }
                  className="px-3 py-1.5 text-sm bg-blue-600 text-white rounded-md hover:bg-blue-700 transition-colors"
                >
                  Retry {selectedCount} Selected
                </button>
              )}
            </div>
          </div>
        </div>

        <div className="divide-y">
          {filteredErrors.length === 0 ? (
            <div className="px-4 py-8 text-center text-gray-500">
              No quarantined festivals in this category
            </div>
          ) : (
            filteredErrors.slice(0, 20).map((festival) => (
              <QuarantinedFestivalItem
                key={festival.id}
                festival={festival}
                onRetry={() => onRetry?.(festival.id)}
              />
            ))
          )}
        </div>

        {filteredErrors.length > 20 && (
          <div className="px-4 py-3 border-t text-center text-sm text-gray-500">
            Showing 20 of {filteredErrors.length} quarantined festivals
          </div>
        )}
      </div>

      {/* Expiring Soon Alert */}
      {dlqStats.expiring_soon > 0 && (
        <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-4 flex items-center gap-3">
          <svg
            className="w-5 h-5 text-yellow-600"
            fill="currentColor"
            viewBox="0 0 20 20"
          >
            <path
              fillRule="evenodd"
              d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z"
              clipRule="evenodd"
            />
          </svg>
          <div className="flex-1">
            <p className="text-sm font-medium text-yellow-800">
              {dlqStats.expiring_soon} festivals will be auto-deleted within 7 days
            </p>
            <p className="text-sm text-yellow-700">
              Quarantined festivals are kept for {dlqStats.retention_days} days before
              automatic cleanup.
            </p>
          </div>
        </div>
      )}
    </div>
  );
}

// DLQ Stats Card
function DLQStatsCard({ stats }: { stats: DLQStats }) {
  return (
    <div className="bg-white rounded-lg border shadow-sm p-4">
      <h3 className="text-sm font-medium text-gray-500 uppercase tracking-wide">
        Quarantine Queue
      </h3>
      <div className="mt-2">
        <span className="text-3xl font-bold text-gray-900">
          {stats.total_quarantined}
        </span>
        <span className="text-sm text-gray-500 ml-2">festivals</span>
      </div>
      <div className="mt-4 space-y-1">
        {Object.entries(stats.by_category).map(([category, count]) => (
          <div key={category} className="flex items-center justify-between text-sm">
            <ErrorCategoryBadge category={category as ErrorCategory} showLabel={true} />
            <span className="text-gray-600">{count}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

// Circuit Breaker Summary Card
function CircuitBreakerSummary({
  breakers,
}: {
  breakers: Record<string, CircuitBreakerMetrics>;
}) {
  const openCount = Object.values(breakers).filter(
    (b) => b.state === "open"
  ).length;
  const halfOpenCount = Object.values(breakers).filter(
    (b) => b.state === "half_open"
  ).length;

  return (
    <div className="bg-white rounded-lg border shadow-sm p-4">
      <h3 className="text-sm font-medium text-gray-500 uppercase tracking-wide">
        Circuit Breakers
      </h3>
      <div className="mt-2">
        <span className="text-3xl font-bold text-gray-900">
          {Object.keys(breakers).length}
        </span>
        <span className="text-sm text-gray-500 ml-2">services</span>
      </div>
      <div className="mt-4 space-y-2">
        {openCount > 0 && (
          <div className="flex items-center gap-2 text-sm text-red-600">
            <span className="w-2 h-2 bg-red-500 rounded-full animate-pulse" />
            <span>{openCount} open (failing fast)</span>
          </div>
        )}
        {halfOpenCount > 0 && (
          <div className="flex items-center gap-2 text-sm text-yellow-600">
            <span className="w-2 h-2 bg-yellow-500 rounded-full" />
            <span>{halfOpenCount} half-open (testing)</span>
          </div>
        )}
        {openCount === 0 && halfOpenCount === 0 && (
          <div className="flex items-center gap-2 text-sm text-green-600">
            <span className="w-2 h-2 bg-green-500 rounded-full" />
            <span>All services healthy</span>
          </div>
        )}
      </div>
    </div>
  );
}

// Error Trend Card
function ErrorTrendCard({ errors }: { errors: FestivalWithValidation[] }) {
  // Group by date (last 7 days)
  const last7Days = Array.from({ length: 7 }, (_, i) => {
    const d = new Date();
    d.setDate(d.getDate() - (6 - i));
    return d.toISOString().split("T")[0];
  });

  const errorsByDay = last7Days.map((date) => ({
    date,
    count: errors.filter((e) =>
      e.first_error_at?.startsWith(date)
    ).length,
  }));

  const maxCount = Math.max(...errorsByDay.map((d) => d.count), 1);

  return (
    <div className="bg-white rounded-lg border shadow-sm p-4">
      <h3 className="text-sm font-medium text-gray-500 uppercase tracking-wide">
        Error Trend (7 days)
      </h3>
      <div className="mt-4 h-24 flex items-end gap-1">
        {errorsByDay.map((day) => (
          <div
            key={day.date}
            className="flex-1 bg-blue-100 rounded-t transition-all hover:bg-blue-200"
            style={{ height: `${(day.count / maxCount) * 100}%` }}
            title={`${day.date}: ${day.count} errors`}
          />
        ))}
      </div>
      <div className="mt-2 flex justify-between text-xs text-gray-400">
        <span>{last7Days[0].slice(5)}</span>
        <span>Today</span>
      </div>
    </div>
  );
}

// Circuit Breaker Detail Card
function CircuitBreakerCard({
  name,
  metrics,
}: {
  name: string;
  metrics: CircuitBreakerMetrics;
}) {
  const stateColors = {
    closed: "bg-green-100 text-green-700 border-green-200",
    open: "bg-red-100 text-red-700 border-red-200",
    half_open: "bg-yellow-100 text-yellow-700 border-yellow-200",
  };

  const stateLabels = {
    closed: "Healthy",
    open: "Open",
    half_open: "Recovering",
  };

  return (
    <div
      className={`p-3 rounded-lg border ${stateColors[metrics.state]}`}
    >
      <div className="flex items-center justify-between">
        <span className="font-medium capitalize">{name}</span>
        <span className="text-xs font-semibold uppercase">
          {stateLabels[metrics.state]}
        </span>
      </div>
      <div className="mt-2 text-sm space-y-1">
        <div className="flex justify-between">
          <span>Success rate:</span>
          <span>
            {metrics.total_calls > 0
              ? Math.round(
                  (metrics.total_successes / metrics.total_calls) * 100
                )
              : 0}
            %
          </span>
        </div>
        <div className="flex justify-between">
          <span>Total calls:</span>
          <span>{metrics.total_calls}</span>
        </div>
        {metrics.last_failure_time && (
          <div className="text-xs opacity-75">
            Last failure: {new Date(metrics.last_failure_time).toLocaleTimeString()}
          </div>
        )}
      </div>
    </div>
  );
}

// Quarantined Festival List Item
function QuarantinedFestivalItem({
  festival,
  onRetry,
}: {
  festival: FestivalWithValidation;
  onRetry?: () => void;
}) {
  return (
    <div className="px-4 py-3 flex items-center justify-between hover:bg-gray-50">
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <h4 className="font-medium text-gray-900 truncate">{festival.name}</h4>
          {festival.error_category && (
            <ErrorCategoryBadge category={festival.error_category} />
          )}
        </div>
        <div className="mt-1 flex items-center gap-3 text-sm text-gray-500">
          <RetryCountBadge count={festival.retry_count} />
          {festival.quarantined_at && (
            <span>
              Quarantined: {new Date(festival.quarantined_at).toLocaleDateString()}
            </span>
          )}
        </div>
        {festival.quarantine_reason && (
          <p className="mt-1 text-sm text-gray-600 truncate">
            {festival.quarantine_reason}
          </p>
        )}
      </div>
      <button
        onClick={onRetry}
        className="ml-4 px-3 py-1.5 text-sm bg-blue-600 text-white rounded-md hover:bg-blue-700 transition-colors"
      >
        Retry
      </button>
    </div>
  );
}