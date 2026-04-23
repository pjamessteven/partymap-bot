import React from 'react'
import { Badge } from '@/components/ui/badge'
import { cn, getStateDescription } from '@/lib/utils'
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
  needs_research_new: { color: 'bg-cyan-500', icon: Search, label: 'Needs Research (New)' },
  needs_research_update: { color: 'bg-cyan-600', icon: Search, label: 'Needs Research (Update)' },
  researching: { color: 'bg-yellow-500', icon: Loader2, label: 'Researching' },
  researched: { color: 'bg-purple-500', icon: CheckCircle2, label: 'Researched' },
  researched_partial: { color: 'bg-amber-500', icon: AlertTriangle, label: 'Researched (Partial)' },
  syncing: { color: 'bg-orange-500', icon: RefreshCw, label: 'Syncing' },
  synced: { color: 'bg-green-500', icon: CircleCheck, label: 'Synced' },
  validating: { color: 'bg-teal-500', icon: Loader2, label: 'Validating' },
  validation_failed: { color: 'bg-red-600', icon: AlertCircle, label: 'Validation Failed' },
  quarantined: { color: 'bg-gray-700', icon: AlertTriangle, label: 'Quarantined' },
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
  const description = getStateDescription(state)

  return (
    <div className="group relative inline-block">
      <Badge
        variant="secondary"
        className={cn(
          `${config.color} text-white gap-1 capitalize cursor-help`,
          className
        )}
      >
        {showIcon && <Icon className="h-3 w-3" />}
        {config.label}
        {children !== undefined && <span className="opacity-90">: {children}</span>}
      </Badge>
      {/* Tooltip */}
      {description && (
        <div className="absolute bottom-full right-0 mb-2 hidden group-hover:block w-56 p-2.5 rounded-lg border bg-card shadow-lg z-20">
          <p className="text-xs font-medium mb-1">{config.label}</p>
          <p className="text-xs text-muted-foreground leading-relaxed">
            {description}
          </p>
        </div>
      )}
    </div>
  )
}
