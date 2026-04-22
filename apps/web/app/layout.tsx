import type { Metadata } from 'next'
import './globals.css'
import { Providers } from './providers'
import { Navigation } from '@/components/navigation'
import { ErrorBoundary } from '@/components/error-boundary'

export const metadata: Metadata = {
  title: 'PartyMap Festival Bot',
  description: 'Automated festival discovery and research bot dashboard',
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-background">
        <ErrorBoundary>
          <Providers>
            <div className="flex min-h-screen">
              <Navigation />
            <main className="flex-1 p-4 pt-20 lg:pt-8 lg:ml-64 lg:p-8">
              {children}
            </main>
            </div>
          </Providers>
        </ErrorBoundary>
      </body>
    </html>
  )
}
