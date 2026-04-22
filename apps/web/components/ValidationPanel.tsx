"use client";

import { useState } from "react";
import {
  ValidationResult,
  ValidationError,
  ValidationStatus,
  FestivalWithValidation,
} from "@/types";
import { ValidationBadge, CompletenessBadge } from "./ValidationBadge";

interface ValidationPanelProps {
  festival: FestivalWithValidation;
  validationResult?: ValidationResult;
  onValidate?: () => void;
  onForceSync?: () => void;
  isLoading?: boolean;
  className?: string;
}

export function ValidationPanel({
  festival,
  validationResult,
  onValidate,
  onForceSync,
  isLoading = false,
  className = "",
}: ValidationPanelProps) {
  const [showDetails, setShowDetails] = useState(true);

  // Use provided result or construct from festival data
  const result: ValidationResult = validationResult || {
    is_valid: festival.validation_status === "ready",
    status: festival.validation_status,
    completeness_score: 0,
    errors: festival.validation_errors || [],
    warnings: festival.validation_warnings || [],
    missing_fields: [],
  };

  const hasErrors = result.errors && result.errors.length > 0;
  const hasWarnings = result.warnings && result.warnings.length > 0;

  const getStatusMessage = (status: ValidationStatus): string => {
    switch (status) {
      case "ready":
        return "This festival is ready to be synced to PartyMap.";
      case "needs_review":
        return "This festival has warnings that should be reviewed before syncing.";
      case "invalid":
        return "This festival has validation errors and cannot be synced.";
      case "pending":
        return "Validation is pending. Click 'Validate' to check data quality.";
      default:
        return "";
    }
  };

  return (
    <div className={`bg-white rounded-lg border shadow-sm ${className}`}>
      {/* Header */}
      <div className="px-4 py-3 border-b flex items-center justify-between">
        <div className="flex items-center gap-3">
          <h3 className="font-semibold text-gray-900">Validation Status</h3>
          <ValidationBadge status={result.status} />
        </div>
        <div className="flex items-center gap-2">
          {onValidate && (
            <button
              onClick={onValidate}
              disabled={isLoading}
              className="px-3 py-1.5 text-sm bg-blue-600 text-white rounded-md hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              {isLoading ? "Validating..." : "Validate"}
            </button>
          )}
          <button
            onClick={() => setShowDetails(!showDetails)}
            className="p-1.5 text-gray-500 hover:text-gray-700 hover:bg-gray-100 rounded-md transition-colors"
            title={showDetails ? "Hide details" : "Show details"}
          >
            <svg
              className={`w-5 h-5 transform transition-transform ${
                showDetails ? "rotate-180" : ""
              }`}
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M19 9l-7 7-7-7"
              />
            </svg>
          </button>
        </div>
      </div>

      {showDetails && (
        <div className="p-4 space-y-4">
          {/* Status Message */}
          <p className="text-sm text-gray-600">{getStatusMessage(result.status)}</p>

          {/* Completeness Score */}
          <div className="flex items-center gap-4 p-3 bg-gray-50 rounded-lg">
            <span className="text-sm font-medium text-gray-700">Completeness:</span>
            <CompletenessBadge score={result.completeness_score} />
            <div className="flex-1 h-2 bg-gray-200 rounded-full overflow-hidden">
              <div
                className={`h-full rounded-full transition-all ${
                  result.completeness_score >= 0.9
                    ? "bg-green-500"
                    : result.completeness_score >= 0.7
                    ? "bg-blue-500"
                    : result.completeness_score >= 0.5
                    ? "bg-yellow-500"
                    : "bg-red-500"
                }`}
                style={{ width: `${result.completeness_score * 100}%` }}
              />
            </div>
          </div>

          {/* Errors Section */}
          {hasErrors && (
            <div className="space-y-2">
              <h4 className="text-sm font-medium text-red-700 flex items-center gap-2">
                <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 20 20">
                  <path
                    fillRule="evenodd"
                    d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7 4a1 1 0 11-2 0 1 1 0 012 0zm-1-9a1 1 0 00-1 1v4a1 1 0 102 0V6a1 1 0 00-1-1z"
                    clipRule="evenodd"
                  />
                </svg>
                Errors ({result.errors.length})
              </h4>
              <ul className="space-y-1">
                {result.errors.map((error, idx) => (
                  <ErrorListItem key={idx} error={error} type="error" />
                ))}
              </ul>
            </div>
          )}

          {/* Warnings Section */}
          {hasWarnings && (
            <div className="space-y-2">
              <h4 className="text-sm font-medium text-yellow-700 flex items-center gap-2">
                <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 20 20">
                  <path
                    fillRule="evenodd"
                    d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z"
                    clipRule="evenodd"
                  />
                </svg>
                Warnings ({result.warnings.length})
              </h4>
              <ul className="space-y-1">
                {result.warnings.map((warning, idx) => (
                  <ErrorListItem key={idx} error={warning} type="warning" />
                ))}
              </ul>
            </div>
          )}

          {/* Missing Fields */}
          {result.missing_fields && result.missing_fields.length > 0 && (
            <div className="space-y-2">
              <h4 className="text-sm font-medium text-gray-700">Missing Fields</h4>
              <div className="flex flex-wrap gap-2">
                {result.missing_fields.map((field) => (
                  <span
                    key={field}
                    className="px-2 py-1 text-xs bg-gray-100 text-gray-700 rounded-md"
                  >
                    {field}
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* Actions */}
          {result.status === "invalid" && onForceSync && (
            <div className="pt-2 border-t">
              <button
                onClick={onForceSync}
                className="text-sm text-orange-600 hover:text-orange-700 font-medium"
              >
                Force sync anyway (not recommended)
              </button>
            </div>
          )}

          {/* Last Checked */}
          {festival.validation_checked_at && (
            <p className="text-xs text-gray-400 text-right">
              Last checked: {new Date(festival.validation_checked_at).toLocaleString()}
            </p>
          )}
        </div>
      )}
    </div>
  );
}

// Error/Warning list item component
interface ErrorListItemProps {
  error: ValidationError;
  type: "error" | "warning";
}

function ErrorListItem({ error, type }: ErrorListItemProps) {
  const bgColor = type === "error" ? "bg-red-50" : "bg-yellow-50";
  const borderColor = type === "error" ? "border-red-200" : "border-yellow-200";
  const textColor = type === "error" ? "text-red-800" : "text-yellow-800";
  const fieldColor = type === "error" ? "text-red-600" : "text-yellow-600";

  return (
    <li className={`p-2 rounded-md border ${bgColor} ${borderColor}`}>
      <div className="flex items-start gap-2">
        <span className={`text-xs font-mono ${fieldColor}`}>{error.field}:</span>
        <span className={`text-sm ${textColor}`}>{error.message}</span>
      </div>
    </li>
  );
}

// Compact validation summary for festival list
interface ValidationSummaryProps {
  festival: FestivalWithValidation;
  showScore?: boolean;
  className?: string;
}

export function ValidationSummary({
  festival,
  showScore = true,
  className = "",
}: ValidationSummaryProps) {
  const errorCount = festival.validation_errors?.length || 0;
  const warningCount = festival.validation_warnings?.length || 0;

  return (
    <div className={`flex items-center gap-2 ${className}`}>
      <ValidationBadge status={festival.validation_status} showLabel={false} />
      {showScore && festival.validation_status !== "pending" && (
        <CompletenessBadge score={(festival.research_data as Record<string, number> | undefined)?.completeness_score || 0} />
      )}
      {errorCount > 0 && (
        <span className="text-xs text-red-600" title={`${errorCount} validation errors`}>
          {errorCount} errors
        </span>
      )}
      {warningCount > 0 && (
        <span className="text-xs text-yellow-600" title={`${warningCount} warnings`}>
          {warningCount} warnings
        </span>
      )}
    </div>
  );
}

// Validation filter for festival list
interface ValidationFilterProps {
  selected: ValidationStatus | "all";
  onChange: (status: ValidationStatus | "all") => void;
  counts?: Record<ValidationStatus | "all", number>;
  className?: string;
}

export function ValidationFilter({
  selected,
  onChange,
  counts,
  className = "",
}: ValidationFilterProps) {
  const options: { value: ValidationStatus | "all"; label: string }[] = [
    { value: "all", label: "All" },
    { value: "ready", label: "Ready" },
    { value: "needs_review", label: "Needs Review" },
    { value: "invalid", label: "Invalid" },
    { value: "pending", label: "Pending" },
  ];

  return (
    <div className={`flex flex-wrap gap-2 ${className}`}>
      {options.map((option) => (
        <button
          key={option.value}
          onClick={() => onChange(option.value)}
          className={`px-3 py-1.5 text-sm rounded-full transition-colors ${
            selected === option.value
              ? "bg-blue-600 text-white"
              : "bg-gray-100 text-gray-700 hover:bg-gray-200"
          }`}
        >
          {option.label}
          {counts && counts[option.value] !== undefined && (
            <span
              className={`ml-1.5 px-1.5 py-0.5 text-xs rounded-full ${
                selected === option.value ? "bg-blue-500" : "bg-gray-200"
              }`}
            >
              {counts[option.value]}
            </span>
          )}
        </button>
      ))}
    </div>
  );
}