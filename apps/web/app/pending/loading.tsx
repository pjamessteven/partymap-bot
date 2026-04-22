import { SkeletonCard, SkeletonList } from '@/components/ui/skeleton'

export default function PendingLoading() {
  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div className="h-9 w-48 bg-muted animate-pulse rounded-md" />
        <div className="h-10 w-24 bg-muted animate-pulse rounded-md" />
      </div>

      <SkeletonCard>
        <div className="flex items-center gap-4">
          <div className="h-4 w-24 bg-muted animate-pulse rounded-md" />
          <div className="h-10 w-48 bg-muted animate-pulse rounded-md" />
        </div>
      </SkeletonCard>

      <SkeletonCard>
        <SkeletonList rows={4} />
      </SkeletonCard>
    </div>
  )
}
