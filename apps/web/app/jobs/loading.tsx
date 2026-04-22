import { SkeletonCard } from '@/components/ui/skeleton'

export default function JobsLoading() {
  return (
    <div className="flex h-[calc(100vh-6rem)] flex-col space-y-4">
      <div className="h-9 w-48 bg-muted animate-pulse rounded-md" />

      <div className="h-10 w-full bg-muted animate-pulse rounded-md" />

      <div className="grid grid-cols-3 gap-4 flex-1">
        <div className="space-y-4">
          <SkeletonCard className="h-48" />
          <SkeletonCard className="h-64" />
        </div>
        <div className="col-span-2 rounded-lg border bg-card">
          <div className="p-6 space-y-4">
            <div className="h-6 w-32 bg-muted animate-pulse rounded-md" />
            <div className="h-4 w-full bg-muted animate-pulse rounded-md" />
            <div className="h-4 w-3/4 bg-muted animate-pulse rounded-md" />
          </div>
        </div>
      </div>
    </div>
  )
}
