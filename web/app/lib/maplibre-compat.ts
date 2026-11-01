import * as maplibreglNamespace from "maplibre-gl/dist/maplibre-gl.mjs";
import "../../node_modules/maplibre-gl/dist/maplibre-gl.css";

const maplibregl: any = {
  ...maplibreglNamespace,
  get workerUrl() {
    return (maplibreglNamespace as any).getWorkerUrl?.();
  },
  set workerUrl(url: string) {
    let resolvedUrl = url;
    // MapLibre v6 removed "dist/maplibre-gl-csp-worker.js" (which returns 404 on unpkg for @latest).
    // Ensure the worker URL resolves to a valid, reachable CDN script.
    if (url && url.includes("dist/maplibre-gl-csp-worker.js") && (url.includes("@latest") || url.includes("@6."))) {
      resolvedUrl = "https://unpkg.com/maplibre-gl@6.16.0/dist/maplibre-gl-worker.mjs";
    }
    if (typeof (maplibreglNamespace as any).setWorkerUrl === "function") {
      (maplibreglNamespace as any).setWorkerUrl(resolvedUrl);
    }
  },
};

export default maplibregl;
export * from "maplibre-gl/dist/maplibre-gl.mjs";
