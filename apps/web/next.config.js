/** @type {import('next').NextConfig} */
const nextConfig = {
  output: process.env.NODE_ENV === 'production' ? 'standalone' : undefined,
  turbopack: {}, // Enable Turbopack (silences webpack warning)
  async rewrites() {
    const apiHost = process.env.API_HOST || 'localhost'
    const apiPort = process.env.API_PORT || '8000'
    return [
      {
        source: '/api/:path*',
        destination: `http://${apiHost}:${apiPort}/api/:path*`,
      },
    ]
  },
}

module.exports = nextConfig
