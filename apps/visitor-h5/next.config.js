/** @type {import('next').NextConfig} */
const localOS = process.env.NEXT_PUBLIC_LOCAL_OS_MODE === '1'
const localCore = process.env.YANTIAN_LOCAL_CORE_URL || 'http://127.0.0.1:8793'
if (localOS && !/^http:\/\/(127\.0\.0\.1|localhost):\d+$/.test(localCore)) {
  throw new Error('本地 OS 的 Core 地址必须是明确的本机 HTTP 端口')
}
const nextConfig = {
  reactStrictMode: true,
  output: 'standalone',
  async rewrites() {
    if (!localOS) return []
    return {
      beforeFiles: [
        { source: '/studio', destination: `${localCore}/studio/` },
        { source: '/studio/:path*', destination: `${localCore}/studio/:path*` },
      ],
      afterFiles: [],
      // Keep Next's own /api/recommendations/home route. Only unmatched APIs
      // reach the isolated Core; no pre-existing Next route is shadowed.
      fallback: [{ source: '/api/:path*', destination: `${localCore}/api/:path*` }],
    }
  },
}

module.exports = nextConfig
