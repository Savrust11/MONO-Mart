/** @type {import('next').NextConfig} */
const nextConfig = {
  output: 'standalone',  // required for Docker / Cloud Run
  experimental: {
    serverComponentsExternalPackages: ['@google-cloud/bigquery'],
    instrumentationHook: true,  // 起動時に GCP_SA_KEY を一時ファイル化（Vercel等ADC無し環境向け）
  },
};

module.exports = nextConfig;
