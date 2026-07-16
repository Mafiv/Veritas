import type { NextConfig } from "next";
import path from "path";

const nextConfig: NextConfig = {
  output: "standalone",
  turbopack: {
    // Keep module resolution inside frontend/
    root: path.resolve(__dirname),
  },
};

export default nextConfig;
