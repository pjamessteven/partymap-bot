import React from 'react'
import { cn } from '@/lib/utils'

interface SkeletonProps {
  className?: string
}

export function Skeleton({ className }: SkeletonProps) {
  return (
    <div
      className={cn(
        'animate-pulse rounded-md bg-muted',
        className
      )}
    />
  )
}

export function SkeletonCard({ className, children }: SkeletonProps & { children?: React.ReactNode }) {
  return (
    <div className={cn('rounded-lg border bg-card p-6 space-y-4', className)}>
      {children ?? (
        <>
          <Skeleton className="h-4 w-1/3" />
          <Skeleton className="h-8 w-2/3" />
        </>
      )}
    </div>
  )
}

export function SkeletonStats({ count = 4 }: { count?: number }) {
  return (
    <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
      {Array.from({ length: count }).map((_, i) => (
        <SkeletonCard key={i} />
      ))}
    </div>
  )
}

export function SkeletonTableRow({ cols = 4 }: { cols?: number }) {
  return (
    <div className="flex items-center gap-4 py-3">
      {Array.from({ length: cols }).map((_, i) => (
        <Skeleton
          key={i}
          className={cn('h-4', i === 0 ? 'flex-1' : 'w-24')}
        />
      ))}
    </div>
  )
}

export function SkeletonList({ rows = 5 }: { rows?: number }) {
  return (
    <div className="space-y-2">
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="rounded-lg border p-4 space-y-2">
          <div className="flex items-center gap-4">
            <Skeleton className="h-3 w-3 rounded-full" />
            <Skeleton className="h-4 flex-1" />
          </div>
          <Skeleton className="h-3 w-2/3" />
        </div>
      ))}
    </div>
  )
}
