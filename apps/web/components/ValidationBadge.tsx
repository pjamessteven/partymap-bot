"use client";

import { ValidationStatus, ErrorCategory } from "@/types";

interface ValidationBadgeProps {
  status: ValidationStatus;
  className?: string;
  showLabel?: boolean;
}

interface ErrorCategoryBadgeProps {
  category?: ErrorCategory;
  className?: string;
  showLabel?: boolean;
}

const validationStyles: Record<ValidationStatus, { bg: string; text: string; label: string; icon: string }> = {
  pending: {
    bg: "bg-gray-100",
    text: "text-gray-600",
    label: "Pending",
    icon: "⏳",
  },
  ready: {
    bg: "bg-green-100",
    text: "text-green-700",
    label: "Ready",
    icon: "✓",
  },
  needs_review: {
    bg: "bg-yellow-100",
    text: "text-yellow-700",
    label: "Needs Review",
    icon: "⚠",
  },
  invalid: {
    bg: "bg-red-100",
    text: "text-red-700",
    label: "Invalid",
    icon: "✕",
  },
};

const errorCategoryStyles: Record<ErrorCategory, { bg: string; text: string; label: string }> = {
  transient: {
    bg: "bg-blue-100",
    text: "text-blue-700",
    label: "Transient",
  },
  permanent: {
    bg: "bg-red-100",
    text: "text-red-700",
    label: "Permanent",
  },
  validation: {
    bg: "bg-orange-100",
    text: "text-orange-700",
    label: "Validation",
  },
  external: {
    bg: "bg-purple-100",
    text: "text-purple-700",
    label: "External",
  },
  budget: {
    bg: "bg-pink-100",
    text: "text-pink-700",
    label: "Budget",
  },
  unknown: {
    bg: "bg-gray-100",
    text: "text-gray-600",
    label: "Unknown",
  },
};

export function ValidationBadge({
  status,
  className = "",
  showLabel = true,
}: ValidationBadgeProps) {
  const style = validationStyles[status];

  return (
    <span
      className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium ${style.bg} ${style.text} ${className}`}
      title={`Validation status: ${style.label}`}
    >
      <span>{style.icon}</span>
      {showLabel && <span>{style.label}</span>}
    </span>
  );
}

export function ErrorCategoryBadge({
  category,
  className = "",
  showLabel = true,
}: ErrorCategoryBadgeProps) {
  if (!category) return null;

  const style = errorCategoryStyles[category];

  return (
    <span
      className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${style.bg} ${style.text} ${className}`}
      title={`Error category: ${style.label}`}
    >
      {showLabel && <span>{style.label}</span>}
    </span>
  );
}

// State badge with validation status combined
interface StateBadgeProps {
  state: string;
  validationStatus?: ValidationStatus;
  isQuarantined?: boolean;
  className?: string;
}

export function StateBadge({
  state,
  validationStatus,
  isQuarantined,
  className = "",
}: StateBadgeProps) {
  // Base state styles
  const stateStyles: Record<string, { bg: string; text: string }> = {
    discovered: { bg: "bg-gray-100", text: "text-gray-700" },
    needs_research_new: { bg: "bg-blue-50", text: "text-blue-700" },
    needs_research_update: { bg: "bg-blue-50", text: "text-blue-700" },
    researching: { bg: "bg-blue-100", text: "text-blue-800" },
    researched: { bg: "bg-green-100", text: "text-green-700" },
    researched_partial: { bg: "bg-yellow-50", text: "text-yellow-700" },
    syncing: { bg: "bg-purple-100", text: "text-purple-700" },
    synced: { bg: "bg-green-100", text: "text-green-700" },
    validating: { bg: "bg-indigo-100", text: "text-indigo-700" },
    validation_failed: { bg: "bg-red-100", text: "text-red-700" },
    quarantined: { bg: "bg-red-200", text: "text-red-800" },
    failed: { bg: "bg-red-100", text: "text-red-700" },
    skipped: { bg: "bg-gray-100", text: "text-gray-600" },
    needs_review: { bg: "bg-orange-100", text: "text-orange-700" },
  };

  const style = stateStyles[state] || { bg: "bg-gray-100", text: "text-gray-700" };

  // Format state name for display
  const formatStateName = (s: string): string => {
    return s
      .split("_")
      .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
      .join(" ");
  };

  return (
    <div className={`inline-flex items-center gap-2 ${className}`}>
      <span
        className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${style.bg} ${style.text}`}
      >
        {formatStateName(state)}
        {isQuarantined && (
          <span className="ml-1" title="Quarantined">🔒</span>
        )}
      </span>
      {validationStatus && state !== "quarantined" && (
        <ValidationBadge status={validationStatus} showLabel={false} />
      )}
    </div>
  );
}

// Retry count badge with visual indicator
interface RetryCountBadgeProps {
  count: number;
  maxRetries?: number;
  className?: string;
}

export function RetryCountBadge({
  count,
  maxRetries = 5,
  className = "",
}: RetryCountBadgeProps) {
  const percentage = Math.min((count / maxRetries) * 100, 100);

  let colorClass = "bg-green-100 text-green-700";
  if (percentage >= 100) {
    colorClass = "bg-red-100 text-red-700";
  } else if (percentage >= 60) {
    colorClass = "bg-orange-100 text-orange-700";
  } else if (percentage >= 40) {
    colorClass = "bg-yellow-100 text-yellow-700";
  }

  return (
    <span
      className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${colorClass} ${className}`}
      title={`Retry ${count} of ${maxRetries}`}
    >
      <svg
        className="w-3 h-3 mr-1"
        fill="none"
        stroke="currentColor"
        viewBox="0 0 24 24"
      >
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth={2}
          d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"
        />
      </svg>
      {count}/{maxRetries}
    </span>
  );
}

// Completeness score badge
interface CompletenessBadgeProps {
  score: number; // 0.0 - 1.0
  className?: string;
}

export function CompletenessBadge({ score, className = "" }: CompletenessBadgeProps) {
  const percentage = Math.round(score * 100);

  let colorClass = "bg-red-100 text-red-700";
  if (percentage >= 90) {
    colorClass = "bg-green-100 text-green-700";
  } else if (percentage >= 70) {
    colorClass = "bg-blue-100 text-blue-700";
  } else if (percentage >= 50) {
    colorClass = "bg-yellow-100 text-yellow-700";
  }

  return (
    <span
      className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${colorClass} ${className}`}
      title={`Data completeness: ${percentage}%`}
    >
      <svg
        className="w-3 h-3 mr-1"
        fill="none"
        stroke="currentColor"
        viewBox="0 0 24 24"
      >
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth={2}
          d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"
        />
      </svg>
      {percentage}%
    </span>
  );
}