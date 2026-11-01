import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Proxy /api/v1/* → FastAPI backend in dev (avoids CORS)
  async rewrites() {
    return [
      {
        source: "/api/v1/:path*",
        destination: `${process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000"}/api/v1/:path*`,
      },
    ];
  },
  turbopack: {
    resolveAlias: {
      "maplibre-gl/dist/maplibre-gl.css": "./node_modules/maplibre-gl/dist/maplibre-gl.css",
      "maplibre-gl": "./app/lib/maplibre-compat.ts",
    },
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
  webpack: (config) => {
    config.resolve = config.resolve || {};
    config.resolve.alias = {
      ...config.resolve.alias,
      "maplibre-gl$": "./app/lib/maplibre-compat.ts",
    };
    return config;
  },
};

export default nextConfig;
