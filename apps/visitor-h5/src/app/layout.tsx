import type { Metadata, Viewport } from 'next'
import './globals.css'
import { LOCAL_OS_MODE } from '@/lib/config'

export const metadata: Metadata = {
  title: '严田 AI 文明引擎',
  description: LOCAL_OS_MODE ? '严田 OS 本地入口：证据问答、文化知识、原创木刻稿样与按版审阅' : '与 AI NPC 对话，探索严田的故事',
  manifest: LOCAL_OS_MODE ? undefined : '/manifest.json',
  icons: LOCAL_OS_MODE ? { icon: "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 40 40'%3E%3Crect width='40' height='40' rx='6' fill='%23315e51'/%3E%3Cpath d='M9 9h22v22H9zm11 0v22M9 20h22' fill='none' stroke='%23fff7e7' stroke-width='2'/%3E%3C/svg%3E" } : undefined,
  appleWebApp: {
    capable: true,
    statusBarStyle: 'default',
    title: '严田',
  },
}

export const viewport: Viewport = {
  width: 'device-width',
  initialScale: 1,
  maximumScale: 1,
  userScalable: false,
  viewportFit: 'cover',
  themeColor: [
    { media: '(prefers-color-scheme: light)', color: '#ffffff' },
    { media: '(prefers-color-scheme: dark)', color: '#0f172a' },
  ],
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="zh-CN">
      <head>
        {!LOCAL_OS_MODE && <>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
        <link
          href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap"
          rel="stylesheet"
        />
        </>}
      </head>
      <body className="antialiased">
        <main className="min-h-screen safe-area-inset-top safe-area-inset-bottom">
          {children}
        </main>
      </body>
    </html>
  )
}
