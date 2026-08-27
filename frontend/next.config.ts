import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // The dev server logged "Blocked cross-origin request to Next.js dev
  // resource /_next/hmr from 127.0.0.1" -- Next.js's dev-mode HMR
  // websocket refuses connections from origins not in this list by
  // default. Confirmed via direct A/B test (same tab, back-to-back
  // reloads): the PriceChart component's chart reliably fails to render
  // via http://127.0.0.1:3000 and reliably succeeds via
  // http://localhost:3000 -- not a random timing race, a deterministic
  // effect of the blocked HMR connection breaking client-side rendering
  // for that origin specifically. Allow 127.0.0.1 explicitly rather than
  // asking anyone to remember to always use "localhost".
  allowedDevOrigins: ["127.0.0.1"],
};

export default nextConfig;
