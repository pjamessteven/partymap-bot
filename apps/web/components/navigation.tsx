'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { cn } from '@/lib/utils'
import {
  LayoutDashboard,
  Music,
  CalendarClock,
  Settings,
  Search,
  DollarSign,
  Activity,
  Zap,
  RefreshCw,
} from 'lucide-react'

const navItems = [
  { href: '/', label: 'Dashboard', icon: LayoutDashboard },
  { href: '/festivals', label: 'Festivals', icon: Music },
  { href: '/pending', label: 'Pending Actions', icon: Activity },
  { href: '/jobs', label: 'Jobs', icon: Zap },
  { href: '/refresh', label: 'Refresh', icon: RefreshCw },
  { href: '/schedule', label: 'Schedule', icon: CalendarClock },
  { href: '/queries', label: 'Discovery Queries', icon: Search },
  { href: '/costs', label: 'Cost Tracking', icon: DollarSign },
  { href: '/settings', label: 'Settings', icon: Settings },
]

export function Navigation() {
  const pathname = usePathname()

  return (
    <nav className="fixed left-0 top-0 h-full w-64 border-r bg-card">
      <div className="p-6">
        <Link href="/" className="flex items-center gap-2">
          <div className="h-8 w-8 rounded-lg bg-primary flex items-center justify-center">
            <Music className="h-5 w-5 text-primary-foreground" />
          </div>
          <span className="text-lg font-bold">PartyMap Bot</span>
        </Link>
      </div>

      <div className="px-3 py-2">
        <div className="space-y-1">
          {navItems.map((item) => {
            const Icon = item.icon
            const isActive = pathname === item.href || pathname.startsWith(`${item.href}/`)

            return (
              <Link
                key={item.href}
                href={item.href}
                className={cn(
                  'flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors',
                  isActive
                    ? 'bg-primary text-primary-foreground'
                    : 'text-muted-foreground hover:bg-muted hover:text-foreground'
                )}
              >
                <Icon className="h-4 w-4" />
                {item.label}
              </Link>
            )
          })}
        </div>
      </div>

      <div className="absolute bottom-0 left-0 right-0 p-4 border-t">
        <div className="text-xs text-muted-foreground">
          <p>API: http://localhost:8000</p>
          <p className="mt-1">v0.1.0</p>
        </div>
      </div>
    </nav>
  )
}
