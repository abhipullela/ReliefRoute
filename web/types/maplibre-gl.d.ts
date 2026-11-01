declare module "maplibre-gl" {
  import type {
    Map as MapClass,
    Marker as MarkerClass,
    Popup as PopupClass,
    LngLatBounds as LngLatBoundsClass,
  } from "maplibre-gl/dist/maplibre-gl";

  export type Map = MapClass;
  export type Marker = MarkerClass;
  export type Popup = PopupClass;
  export type LngLatBounds = LngLatBoundsClass;

  const maplibregl: {
    Map: typeof MapClass;
    Marker: typeof MarkerClass;
    Popup: typeof PopupClass;
    LngLatBounds: typeof LngLatBoundsClass;
    workerUrl?: string;
    setWorkerUrl?: (url: string) => void;
    [key: string]: any;
  };

  export default maplibregl;
}

declare module "maplibre-gl/dist/maplibre-gl.mjs" {
  export * from "maplibre-gl/dist/maplibre-gl";
}
