/** @type {import('next').NextConfig} */
const nextConfig = {
  output: 'standalone',  // required for Docker / Cloud Run
  experimental: {
    serverComponentsExternalPackages: ['@google-cloud/bigquery'],
  },
};

module.exports = nextConfig;
