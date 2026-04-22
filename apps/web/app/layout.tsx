import type { Metadata } from 'next'
import './globals.css'
import { Providers } from './providers'
import { Navigation } from '@/components/navigation'

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
        <Providers>
          <div className="flex min-h-screen">
            <Navigation />
            <main className="flex-1 ml-64 p-8">
              {children}
            </main>
          </div>
        </Providers>
      </body>
    </html>
  )
}
