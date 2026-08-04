export const metadata = {
  title: "DMA Insights",
  description: "Digital Maturity Assessment insights",
};

// Design tokens verbatim from prototype/template.html — the prototype is
// authoritative for layout and visual rendering.
const tokens = `
:root{
  --z-navy:#001E48;--z-dark:#1C4A4D;--z-teal:#27BBAF;--z-mid:#139F94;
  --z-lt-teal:#62D7B8;--z-mint:#79E2BF;--z-mint-lt:#B0EDD3;--z-ice:#E8F7F6;
  --z-lav:#F2F4F9;--z-blue:#3D81F6;--z-lt-blue:#A5C6FF;--z-purple:#8094C0;
  --z-dpur:#735BA1;--z-below:#C25008;--z-above:#059669;--z-org:#FE9732;
  --z-org-lt:#FFCB99;--z-bg:#F5F5F5;--z-sep:#E5E7EB;--z-body:#4A5568;
  --z-muted:#6B7280;--z-white:#FFFFFF;
  --r-xs:3px;--r-sm:4px;--r:8px;--r-lg:12px;--r-xl:16px;
  --sh-sm:0 1px 2px rgba(28,74,77,.06);--sh-md:0 4px 14px rgba(28,74,77,.08);
  --sh-lg:0 10px 30px rgba(28,74,77,.12);
  --font-sans:'DM Sans',-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
}
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:var(--font-sans);background:var(--z-bg);color:var(--z-body);
     -webkit-font-smoothing:antialiased}
a{color:inherit;text-decoration:none}
`;

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link
          href="https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;700&display=swap"
          rel="stylesheet"
        />
        <style dangerouslySetInnerHTML={{ __html: tokens }} />
      </head>
      <body>{children}</body>
    </html>
  );
}
