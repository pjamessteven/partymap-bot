import { SkeletonStats, SkeletonCard, SkeletonList } from '@/components/ui/skeleton'

export default function DashboardLoading() {
  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div className="h-9 w-48 bg-muted animate-pulse rounded-md" />
        <div className="h-10 w-36 bg-muted animate-pulse rounded-md" />
      </div>

      <SkeletonStats count={4} />

      <SkeletonCard className="space-y-3">
        <div className="flex gap-2">
          <div className="h-6 w-24 bg-muted animate-pulse rounded-full" />
          <div className="h-6 w-24 bg-muted animate-pulse rounded-full" />
          <div className="h-6 w-24 bg-muted animate-pulse rounded-full" />
        </div>
      </SkeletonCard>

      <SkeletonCard className="space-y-3">
        <div className="grid grid-cols-4 gap-4">
          <div className="h-16 bg-muted animate-pulse rounded-md" />
          <div className="h-16 bg-muted animate-pulse rounded-md" />
          <div className="h-16 bg-muted animate-pulse rounded-md" />
          <div className="h-16 bg-muted animate-pulse rounded-md" />
        </div>
      </SkeletonCard>

      <SkeletonCard>
        <SkeletonList rows={3} />
      </SkeletonCard>
    </div>
  )
}
