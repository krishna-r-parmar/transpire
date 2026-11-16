import type { Metadata, Viewport } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "TRANSPIRE | Ideate. Transform. Inspire.",
  description:
    "TRANSPIRE turns employee ideas into governed, measurable improvement across the organisation.",
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  viewportFit: "cover",
  themeColor: "#f7f9fc",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" suppressHydrationWarning data-scroll-behavior="smooth">
      <head>
        <script
          dangerouslySetInnerHTML={{
            __html:
              "try{var t=localStorage.getItem('transpire-theme');document.documentElement.dataset.theme=t==='dark'?'dark':'light'}catch(e){document.documentElement.dataset.theme='light'}try{document.documentElement.dataset.sidebar=localStorage.getItem('transpire-sidebar')==='collapsed'?'collapsed':'expanded'}catch(e){document.documentElement.dataset.sidebar='expanded'}",
          }}
        />
      </head>
      <body>{children}</body>
    </html>
  );
}
