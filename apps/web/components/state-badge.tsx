import React from 'react'
import { Badge } from '@/components/ui/badge'
import { cn } from '@/lib/utils'
import {
  Search,
  Loader2,
  CheckCircle2,
  RefreshCw,
  CircleCheck,
  AlertCircle,
  SkipForward,
  AlertTriangle,
  CircleDot,
  type LucideIcon,
} from 'lucide-react'

const stateConfig: Record<
  string,
  { color: string; icon: LucideIcon; label: string }
> = {
  discovered: { color: 'bg-blue-500', icon: Search, label: 'Discovered' },
  researching: { color: 'bg-yellow-500', icon: Loader2, label: 'Researching' },
  researched: { color: 'bg-purple-500', icon: CheckCircle2, label: 'Researched' },
  syncing: { color: 'bg-orange-500', icon: RefreshCw, label: 'Syncing' },
  synced: { color: 'bg-green-500', icon: CircleCheck, label: 'Synced' },
  failed: { color: 'bg-red-500', icon: AlertCircle, label: 'Failed' },
  skipped: { color: 'bg-gray-500', icon: SkipForward, label: 'Skipped' },
  needs_review: { color: 'bg-pink-500', icon: AlertTriangle, label: 'Needs Review' },
}

interface StateBadgeProps {
  state: string
  showIcon?: boolean
  className?: string
  children?: React.ReactNode
}

export function StateBadge({ state, showIcon = true, className, children }: StateBadgeProps) {
  const config = stateConfig[state] || { color: 'bg-gray-500', icon: CircleDot, label: state }
  const Icon = config.icon

  return (
    <Badge
      variant="secondary"
      className={cn(
        `${config.color} text-white gap-1 capitalize`,
        className
      )}
    >
      {showIcon && <Icon className="h-3 w-3" />}
      {config.label}
      {children !== undefined && <span className="opacity-90">: {children}</span>}
    </Badge>
  )
}
