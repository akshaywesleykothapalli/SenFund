import { fileURLToPath } from "node:url";
export default {
  devIndicators: false,
  poweredByHeader: false,
  turbopack: { root: fileURLToPath(new URL(".", import.meta.url)) },
  // Railway: the static checkout runs on loopback :8702 inside the same container.
  async rewrites() {
    return [{ source: "/checkout/:path*", destination: "http://127.0.0.1:8702/:path*" }];
  },
};
