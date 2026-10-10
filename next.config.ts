import type { NextConfig } from "next";

const config: NextConfig = {
  serverExternalPackages: ["@electric-sql/pglite"],
  outputFileTracingIncludes: {
    "/**": ["./supabase/migrations/**/*", "./supabase/dev/**/*"],
  },
  images: {
    remotePatterns: [
      { protocol: "https", hostname: "picsum.photos" },
      { protocol: "https", hostname: "*.supabase.co" },
      { protocol: "https", hostname: "lh3.googleusercontent.com" },
    ],
  },
  experimental: { serverActions: { bodySizeLimit: "6mb" } },
};

export default config;
