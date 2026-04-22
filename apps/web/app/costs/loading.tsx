import { SkeletonCard } from '@/components/ui/skeleton'

export default function CostsLoading() {
  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div className="h-9 w-40 bg-muted animate-pulse rounded-md" />
        <div className="h-10 w-48 bg-muted animate-pulse rounded-md" />
      </div>

      <div className="grid gap-4 md:grid-cols-3">
        <SkeletonCard />
        <SkeletonCard />
        <SkeletonCard />
      </div>

      <SkeletonCard className="h-24" />
      <SkeletonCard className="h-24" />
      <SkeletonCard>
        <div className="space-y-3">
          <div className="h-12 bg-muted animate-pulse rounded-md" />
          <div className="h-12 bg-muted animate-pulse rounded-md" />
          <div className="h-12 bg-muted animate-pulse rounded-md" />
        </div>
      </SkeletonCard>
    </div>
  )
}
