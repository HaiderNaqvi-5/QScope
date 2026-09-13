import type { NextConfig } from 'next';

const nextConfig: NextConfig = {
  reactStrictMode: true,
  swcMinify: true,
  
  // TypeScript strict mode
  typescript: {
    tsconfigPath: './tsconfig.json',
  },

  // Environment variables
  env: {
    NEXT_PUBLIC_API_URL: process.env.FRONTEND_NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8000',
  },

  // Headers for security
  async headers() {
    return [
      {
        source: '/:path*',
        headers: [
          {
            key: 'X-Content-Type-Options',
            value: 'nosniff',
          },
          {
            key: 'X-Frame-Options',
            value: 'SAMEORIGIN',
          },
          {
            key: 'X-XSS-Protection',
            value: '1; mode=block',
          },
          {
            key: 'Referrer-Policy',
            value: 'strict-origin-when-cross-origin',
          },
        ],
      },
    ];
  },

  // Redirect trailing slashes
  trailingSlash: false,

  // Experimental features
  experimental: {
    esmExternals: true,
  },

  // Build configuration
  onDemandEntries: {
    maxInactiveAge: 25 * 1000,
    pagesBufferLength: 2,
  },

  // Image optimization
  images: {
    unoptimized: true, // For local development
  },

  // Webpack configuration
  webpack: (config) => {
    return config;
  },
};

export default nextConfig;
