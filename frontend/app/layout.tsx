import type { Metadata } from 'next'
import { Inter } from 'next/font/google'
import NavBar from '@/components/NavBar'
import './globals.css'

const inter = Inter({ subsets: ['latin'], variable: '--font-inter', display: 'swap' })

export const metadata: Metadata = {
  title: {
    default: 'TNWatch — Tamil Nadu Civic Accountability',
    template: '%s | TNWatch',
  },
  description:
    "Independent, data-driven civic accountability for Tamil Nadu. Track your MLA's profile, assets, and performance — with sourced public records.",
  keywords: ['Tamil Nadu', 'MLA', 'legislative assembly', 'civic accountability', 'TNWatch'],
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={inter.variable}>
      <body className="min-h-screen bg-gray-50 antialiased">
        <NavBar />
        <main className="min-h-[calc(100vh-4rem)]">{children}</main>
        <footer className="mt-16 border-t border-gray-200 bg-white py-8">
          <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
            <p className="text-center text-xs text-gray-400">
              TNWatch — Independent civic accountability for Tamil Nadu. Data sourced from public
              records only. Facts with sources; no opinions or accusations.
            </p>
          </div>
        </footer>
      </body>
    </html>
  )
}
