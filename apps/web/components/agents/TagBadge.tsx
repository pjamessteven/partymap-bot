"use client";

import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

// Consistent color palette for known festival tags/genres
const TAG_COLORS: Record<string, string> = {
  psytrance: "bg-purple-100 text-purple-800 hover:bg-purple-200 dark:bg-purple-900 dark:text-purple-200",
  techno: "bg-red-100 text-red-800 hover:bg-red-200 dark:bg-red-900 dark:text-red-200",
  house: "bg-blue-100 text-blue-800 hover:bg-blue-200 dark:bg-blue-900 dark:text-blue-200",
  trance: "bg-indigo-100 text-indigo-800 hover:bg-indigo-200 dark:bg-indigo-900 dark:text-indigo-200",
  dubstep: "bg-orange-100 text-orange-800 hover:bg-orange-200 dark:bg-orange-900 dark:text-orange-200",
  reggae: "bg-green-100 text-green-800 hover:bg-green-200 dark:bg-green-900 dark:text-green-200",
  drumandbass: "bg-yellow-100 text-yellow-800 hover:bg-yellow-200 dark:bg-yellow-900 dark:text-yellow-200",
  dnb: "bg-yellow-100 text-yellow-800 hover:bg-yellow-200 dark:bg-yellow-900 dark:text-yellow-200",
  ambient: "bg-teal-100 text-teal-800 hover:bg-teal-200 dark:bg-teal-900 dark:text-teal-200",
  electronic: "bg-cyan-100 text-cyan-800 hover:bg-cyan-200 dark:bg-cyan-900 dark:text-cyan-200",
  "hip hop": "bg-pink-100 text-pink-800 hover:bg-pink-200 dark:bg-pink-900 dark:text-pink-200",
  hiphop: "bg-pink-100 text-pink-800 hover:bg-pink-200 dark:bg-pink-900 dark:text-pink-200",
  rock: "bg-stone-100 text-stone-800 hover:bg-stone-200 dark:bg-stone-900 dark:text-stone-200",
  jazz: "bg-amber-100 text-amber-800 hover:bg-amber-200 dark:bg-amber-900 dark:text-amber-200",
  folk: "bg-emerald-100 text-emerald-800 hover:bg-emerald-200 dark:bg-emerald-900 dark:text-emerald-200",
  blues: "bg-sky-100 text-sky-800 hover:bg-sky-200 dark:bg-sky-900 dark:text-sky-200",
  metal: "bg-neutral-100 text-neutral-800 hover:bg-neutral-200 dark:bg-neutral-900 dark:text-neutral-200",
  pop: "bg-rose-100 text-rose-800 hover:bg-rose-200 dark:bg-rose-900 dark:text-rose-200",
  world: "bg-lime-100 text-lime-800 hover:bg-lime-200 dark:bg-lime-900 dark:text-lime-200",
};

function getTagColor(tag: string): string {
  const normalized = tag.toLowerCase().replace(/[^a-z]/g, "");
  return (
    TAG_COLORS[normalized] ||
    TAG_COLORS[tag.toLowerCase()] ||
    "bg-secondary text-secondary-foreground hover:bg-secondary/80"
  );
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
  // Tags can be nested in various places depending on the data structure
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
