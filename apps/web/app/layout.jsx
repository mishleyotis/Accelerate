export const metadata = {
  title: "DMA Insights",
  description: "Digital Maturity Assessment insights",
};

// The full prototype stylesheet (tokens + app styles + self-hosted DM
// Sans) — extracted verbatim from prototype/template.html; the prototype
// is authoritative for visual rendering.

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <head>
        <link rel="stylesheet" href="/proto/app.css" />
        <link rel="icon" href="/brand/icon_teal.png" />
      </head>
      <body>{children}</body>
    </html>
  );
}
