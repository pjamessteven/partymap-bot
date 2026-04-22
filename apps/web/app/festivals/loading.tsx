import { SkeletonCard, SkeletonList } from '@/components/ui/skeleton'

export default function FestivalsLoading() {
  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div className="h-9 w-40 bg-muted animate-pulse rounded-md" />
        <div className="h-10 w-32 bg-muted animate-pulse rounded-md" />
      </div>

      <SkeletonCard>
        <div className="flex gap-4">
          <div className="h-10 flex-1 bg-muted animate-pulse rounded-md" />
          <div className="h-10 w-48 bg-muted animate-pulse rounded-md" />
          <div className="h-10 w-24 bg-muted animate-pulse rounded-md" />
        </div>
      </SkeletonCard>

      <SkeletonCard>
        <SkeletonList rows={5} />
      </SkeletonCard>
    </div>
  )
}
