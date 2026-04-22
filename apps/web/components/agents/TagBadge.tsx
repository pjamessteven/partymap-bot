"use client";

import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

// Pleasant pastel palette — colors are assigned deterministically by tag hash
const PALETTE = [
  "bg-slate-100 text-slate-700 hover:bg-slate-200 dark:bg-slate-800 dark:text-slate-200",
  "bg-zinc-100 text-zinc-700 hover:bg-zinc-200 dark:bg-zinc-800 dark:text-zinc-200",
  "bg-stone-100 text-stone-700 hover:bg-stone-200 dark:bg-stone-800 dark:text-stone-200",
  "bg-red-100 text-red-700 hover:bg-red-200 dark:bg-red-900 dark:text-red-200",
  "bg-orange-100 text-orange-700 hover:bg-orange-200 dark:bg-orange-900 dark:text-orange-200",
  "bg-amber-100 text-amber-700 hover:bg-amber-200 dark:bg-amber-900 dark:text-amber-200",
  "bg-yellow-100 text-yellow-700 hover:bg-yellow-200 dark:bg-yellow-900 dark:text-yellow-200",
  "bg-lime-100 text-lime-700 hover:bg-lime-200 dark:bg-lime-900 dark:text-lime-200",
  "bg-green-100 text-green-700 hover:bg-green-200 dark:bg-green-900 dark:text-green-200",
  "bg-emerald-100 text-emerald-700 hover:bg-emerald-200 dark:bg-emerald-900 dark:text-emerald-200",
  "bg-teal-100 text-teal-700 hover:bg-teal-200 dark:bg-teal-900 dark:text-teal-200",
  "bg-cyan-100 text-cyan-700 hover:bg-cyan-200 dark:bg-cyan-900 dark:text-cyan-200",
  "bg-sky-100 text-sky-700 hover:bg-sky-200 dark:bg-sky-900 dark:text-sky-200",
  "bg-blue-100 text-blue-700 hover:bg-blue-200 dark:bg-blue-900 dark:text-blue-200",
  "bg-indigo-100 text-indigo-700 hover:bg-indigo-200 dark:bg-indigo-900 dark:text-indigo-200",
  "bg-violet-100 text-violet-700 hover:bg-violet-200 dark:bg-violet-900 dark:text-violet-200",
  "bg-purple-100 text-purple-700 hover:bg-purple-200 dark:bg-purple-900 dark:text-purple-200",
  "bg-fuchsia-100 text-fuchsia-700 hover:bg-fuchsia-200 dark:bg-fuchsia-900 dark:text-fuchsia-200",
  "bg-pink-100 text-pink-700 hover:bg-pink-200 dark:bg-pink-900 dark:text-pink-200",
  "bg-rose-100 text-rose-700 hover:bg-rose-200 dark:bg-rose-900 dark:text-rose-200",
];

function hashString(str: string): number {
  let hash = 0;
  for (let i = 0; i < str.length; i++) {
    const char = str.charCodeAt(i);
    hash = (hash << 5) - hash + char;
    hash |= 0; // Convert to 32-bit integer
  }
  return Math.abs(hash);
}

function getTagColor(tag: string): string {
  const idx = hashString(tag.toLowerCase().trim()) % PALETTE.length;
  return PALETTE[idx];
}

export function TagBadge({
  tag,
  className,
  onClick,
}: {
  tag: string;
  className?: string;
  onClick?: () => void;
}) {
  return (
    <Badge
      variant="secondary"
      className={cn(
        "text-xs font-normal cursor-default",
        getTagColor(tag),
        onClick && "cursor-pointer",
        className
      )}
      onClick={onClick}
    >
      {tag}
    </Badge>
  );
}

export function TagList({
  tags,
  className,
  max = 0,
  onTagClick,
}: {
  tags?: string[];
  className?: string;
  max?: number;
  onTagClick?: (tag: string) => void;
}) {
  if (!tags || tags.length === 0) return null;

  const display = max > 0 ? tags.slice(0, max) : tags;
  const remaining = max > 0 ? tags.length - max : 0;

  return (
    <div className={cn("flex flex-wrap gap-1.5", className)}>
      {display.map((tag) => (
        <TagBadge key={tag} tag={tag} onClick={onTagClick ? () => onTagClick(tag) : undefined} />
      ))}
      {remaining > 0 && (
        <Badge variant="outline" className="text-xs font-normal">
          +{remaining} more
        </Badge>
      )}
    </div>
  );
}

export function extractTagsFromResearchData(
  researchData?: Record<string, unknown> | null
): string[] {
  if (!researchData) return [];
  const possiblePaths = [
    (researchData as any).festival_data?.tags,
    (researchData as any).tags,
    (researchData as any).data?.tags,
  ];
  for (const tags of possiblePaths) {
    if (Array.isArray(tags) && tags.length > 0) {
      return tags.filter((t): t is string => typeof t === "string");
    }
  }
  return [];
}
