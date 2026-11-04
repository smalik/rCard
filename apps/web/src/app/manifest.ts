import type { MetadataRoute } from "next";

// Lets people install Plytos on their phone's home screen.
export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "Plytos",
    short_name: "Plytos",
    description: "Play to your strengths.",
    start_url: "/cards",
    scope: "/",
    display: "standalone",
    orientation: "portrait",
    background_color: "#fbf6ee",
    theme_color: "#fbf6ee",
    icons: [{ src: "/icon.svg", sizes: "any", type: "image/svg+xml", purpose: "any" }],
  };
}
