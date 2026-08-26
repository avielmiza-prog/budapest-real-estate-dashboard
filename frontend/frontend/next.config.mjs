/** @type {import('next').NextConfig} */
const nextConfig = {
  images: {
    // Listing photos are hotlinked from whichever portal they were scraped
    // from — allow any https host rather than hardcoding one portal's CDN.
    // Tighten this to specific hostnames once you know which portals you're
    // actually pulling images from in production.
    remotePatterns: [{ protocol: "https", hostname: "**" }],
  },
};

export default nextConfig;
