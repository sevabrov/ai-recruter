import type { Metadata } from "next";
import { IBM_Plex_Mono, IBM_Plex_Sans, Instrument_Sans } from "next/font/google";
import { notFound } from "next/navigation";
import { hasLocale, NextIntlClientProvider } from "next-intl";
import { getTranslations, setRequestLocale } from "next-intl/server";
import { themeBootstrapScript } from "@/lib/theme-provider";
import { Providers } from "@/lib/providers";
import { routing } from "@/i18n/routing";
import "../globals.css";

const instrument = Instrument_Sans({
  subsets: ["latin", "latin-ext"],
  variable: "--font-instrument",
  weight: ["500", "600", "700"],
  display: "swap",
});

const plexSans = IBM_Plex_Sans({
  subsets: ["latin", "latin-ext", "cyrillic"],
  variable: "--font-plex-sans",
  weight: ["400", "500", "600"],
  display: "swap",
});

const plexMono = IBM_Plex_Mono({
  subsets: ["latin", "latin-ext", "cyrillic"],
  variable: "--font-plex-mono",
  weight: ["400", "500"],
  display: "swap",
});

export function generateStaticParams() {
  return routing.locales.map((locale) => ({ locale }));
}

type LocaleParams = { params: Promise<{ locale: string }> };

export async function generateMetadata({ params }: LocaleParams): Promise<Metadata> {
  const { locale } = await params;
  const t = await getTranslations({ locale, namespace: "meta" });

  return {
    title: t("title"),
    description: t("description"),
  };
}

export default async function LocaleLayout({
  children,
  params,
}: LocaleParams & { children: React.ReactNode }) {
  const { locale } = await params;
  if (!hasLocale(routing.locales, locale)) notFound();

  // Lets every page below render statically instead of opting into dynamic
  // rendering the first time a translation is read.
  setRequestLocale(locale);

  return (
    <html lang={locale} suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: themeBootstrapScript }} />
      </head>
      <body
        className={`${instrument.variable} ${plexSans.variable} ${plexMono.variable}`}
        suppressHydrationWarning
      >
        {/* Locale, messages and formats are read from i18n/request.ts and handed
            to the client tree — the app is almost entirely client components. */}
        <NextIntlClientProvider>
          <Providers>{children}</Providers>
        </NextIntlClientProvider>
      </body>
    </html>
  );
}
