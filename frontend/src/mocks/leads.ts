/**
 * MOCK LEAD POOL
 * ==============
 * Curated fixtures, not random noise: every lead carries the same shape the
 * FastAPI backend will return, including per-signal evidence and its source
 * URL. Scores are NOT hand-written — they are computed from signal confidence
 * times the configured weights, mirroring the Phase 6 rule "the LLM detects
 * signals, the backend computes the score".
 */

import { DEFAULT_SIGNAL_WEIGHTS } from "@/lib/domain";
import { computeScore } from "@/lib/scoring";
import type {
  GeoLocation,
  Lead,
  LeadContacts,
  LeadPlatform,
  LeadSignal,
  LeadSource,
  LeadStatus,
  Platform,
  SignalType,
} from "@/services/types";

/** Fixtures are dated relative to load time so "2h ago" stays believable. */
const NOW = new Date();
const HOUR = 3_600_000;

function isoHoursAgo(hours: number) {
  return new Date(NOW.getTime() - hours * HOUR).toISOString();
}

type SignalSeed = {
  confidence: number;
  evidence: string;
  source: Platform;
};

type SourceSeed = {
  platform: Platform;
  url: string;
  title: string;
  snippet: string;
};

type LeadSeed = {
  id: string;
  searchId: string;
  name: string;
  headline: string;
  company?: string;
  location: GeoLocation;
  languages: string[];
  platforms: LeadPlatform[];
  summary: string;
  signals: Partial<Record<SignalType, SignalSeed>>;
  contacts?: LeadContacts;
  sources?: SourceSeed[];
  status?: LeadStatus;
  saved?: boolean;
  hoursAgo: number;
};

const SEARCH_NAMES: Record<string, string> = {
  srch_es_mihi: "MIHI Beauty Leaders Spain",
  srch_de_mihi: "MIHI distributors — Germany",
  srch_it_beauty: "Beauty founders — Italy",
  srch_pl_network: "Network Marketing Leaders — Poland",
};

function platformUrl(platform: Platform, handle: string): string {
  switch (platform) {
    case "instagram":
      return `https://www.instagram.com/${handle}/`;
    case "linkedin":
      return `https://www.linkedin.com/in/${handle}/`;
    case "facebook":
      return `https://www.facebook.com/${handle}`;
    case "threads":
      return `https://www.threads.net/@${handle}`;
    default:
      return `https://${handle}`;
  }
}

function ig(handle: string, followers: number): LeadPlatform {
  return { platform: "instagram", handle: `@${handle}`, url: platformUrl("instagram", handle), followers };
}
function li(handle: string, followers?: number): LeadPlatform {
  return { platform: "linkedin", handle, url: platformUrl("linkedin", handle), followers };
}
function fb(handle: string, followers?: number): LeadPlatform {
  return { platform: "facebook", handle, url: platformUrl("facebook", handle), followers };
}
function th(handle: string, followers?: number): LeadPlatform {
  return { platform: "threads", handle: `@${handle}`, url: platformUrl("threads", handle), followers };
}
function site(domain: string): LeadPlatform {
  return { platform: "website", handle: domain, url: `https://${domain}` };
}
function blog(domain: string): LeadPlatform {
  return { platform: "blog", handle: domain, url: `https://${domain}` };
}

const SEEDS: LeadSeed[] = [
  {
    id: "lead_anna_kowalska",
    searchId: "srch_es_mihi",
    name: "Anna Kowalska",
    headline: "Beauty team leader · MIHI Iberia",
    company: "MIHI",
    location: { country: "Spain", city: "Barcelona", region: "Catalonia" },
    languages: ["Spanish", "Polish", "English"],
    platforms: [ig("anna.beautyteam", 24800), li("anna-kowalska-beauty", 3100), site("annakowalska.es")],
    summary:
      "Anna appears to be an experienced network marketing professional focused on beauty and cosmetics. Her public activity indicates active recruiting and team-building across Spain and Poland, with a personal site used as a landing page for applications.",
    signals: {
      mlm: {
        confidence: 0.98,
        evidence: "\"7 años en network marketing — construyendo equipos en España y Polonia\"",
        source: "instagram",
      },
      beauty: {
        confidence: 0.96,
        evidence: "Bio reads \"skincare & cosmética natural\"; 80% of recent posts are product routines.",
        source: "instagram",
      },
      recruiting: {
        confidence: 0.94,
        evidence: "\"Busco 3 personas para mi equipo este mes — escríbeme 'EQUIPO'\" (posted 4 days ago)",
        source: "instagram",
      },
      leadership: {
        confidence: 0.9,
        evidence: "\"Liderando un equipo internacional de 40+ consultoras de belleza\"",
        source: "linkedin",
      },
      location: { confidence: 1, evidence: "Profile location: Barcelona, Spain. Posts geotagged in Barcelona.", source: "instagram" },
      personalBrand: {
        confidence: 0.85,
        evidence: "Personal domain annakowalska.es with an application form and press mentions.",
        source: "website",
      },
      activity: { confidence: 0.93, evidence: "18 posts and 40+ stories in the last 30 days.", source: "instagram" },
    },
    contacts: { email: "hola@annakowalska.es", website: "https://annakowalska.es" },
    status: "qualified",
    saved: true,
    hoursAgo: 3,
  },
  {
    id: "lead_maria_petrova",
    searchId: "srch_es_mihi",
    name: "María Petrova",
    headline: "Regional director · cosmetics distribution",
    company: "Nuvia Cosmetics",
    location: { country: "Spain", city: "Madrid" },
    languages: ["Spanish", "Russian", "English"],
    platforms: [li("maria-petrova-md", 6400), ig("maria.petrova.md", 11200)],
    summary:
      "Maria runs a multi-country distribution structure for a cosmetics brand. LinkedIn shows a decade of direct-sales leadership; her public posts regularly announce onboarding cohorts for new distributors.",
    signals: {
      mlm: { confidence: 0.95, evidence: "\"Direct sales & network marketing — 10 years, 4 countries\"", source: "linkedin" },
      beauty: { confidence: 0.94, evidence: "Current role listed as Regional Director, cosmetics distribution.", source: "linkedin" },
      recruiting: {
        confidence: 0.88,
        evidence: "\"Открываю новый набор в команду с сентября\" (recruiting cohort announcement)",
        source: "instagram",
      },
      leadership: { confidence: 0.92, evidence: "\"Managing 6 city teams across Spain and Portugal\"", source: "linkedin" },
      location: { confidence: 1, evidence: "LinkedIn location: Madrid, Community of Madrid, Spain.", source: "linkedin" },
      personalBrand: { confidence: 0.6, evidence: "Speaks at industry events; no personal domain found.", source: "linkedin" },
      activity: { confidence: 0.8, evidence: "Posts 2–3 times per week on LinkedIn.", source: "linkedin" },
    },
    contacts: { email: "m.petrova@nuvia-team.es" },
    status: "reviewed",
    saved: true,
    hoursAgo: 4,
  },
  {
    id: "lead_elena_rossi",
    searchId: "srch_es_mihi",
    name: "Elena Rossi",
    headline: "Beauty consultant & content creator",
    location: { country: "Spain", city: "Valencia" },
    languages: ["Spanish", "Italian"],
    platforms: [ig("elena.glowlab", 18300), th("elena.glowlab", 2200)],
    summary:
      "Elena is an active beauty content creator selling through a network marketing structure. Recruiting language is present but no team leadership evidence was found in public sources.",
    signals: {
      mlm: { confidence: 0.86, evidence: "\"Consultora independiente\" plus a personal referral shop link.", source: "instagram" },
      beauty: { confidence: 0.97, evidence: "Feed is entirely skincare routines and product comparisons.", source: "instagram" },
      recruiting: { confidence: 0.72, evidence: "\"¿Quieres unirte? Link en bio\" in three recent captions.", source: "instagram" },
      location: { confidence: 1, evidence: "Bio: \"Valencia 🇪🇸\"; stories geotagged in Valencia.", source: "instagram" },
      personalBrand: { confidence: 0.78, evidence: "Consistent visual identity, 18k followers, brand collaborations.", source: "instagram" },
      activity: { confidence: 0.95, evidence: "Daily stories, 22 posts in the last 30 days.", source: "instagram" },
    },
    status: "new",
    hoursAgo: 5,
  },
  {
    id: "lead_carmen_delgado",
    searchId: "srch_es_mihi",
    name: "Carmen Delgado",
    headline: "Founder · beauty team academy",
    company: "Delgado Beauty Academy",
    location: { country: "Spain", city: "Seville", region: "Andalusia" },
    languages: ["Spanish", "English"],
    platforms: [ig("carmendelgado.academy", 31500), site("delgadoacademy.es"), fb("delgado.beauty.academy", 8900)],
    summary:
      "Carmen trains beauty consultants through her own academy while leading a distributor network. Strong evidence of both leadership and structured recruiting funnels.",
    signals: {
      mlm: { confidence: 0.93, evidence: "\"Mi equipo de distribución cubre Andalucía y Canarias\"", source: "website" },
      beauty: { confidence: 0.95, evidence: "Academy curriculum covers cosmetics and skincare retail.", source: "website" },
      recruiting: { confidence: 0.96, evidence: "Public application form: \"Únete a mi equipo — plazas limitadas\".", source: "website" },
      leadership: { confidence: 0.94, evidence: "\"Formando a más de 200 consultoras desde 2019\"", source: "instagram" },
      location: { confidence: 1, evidence: "Business address in Seville listed on the academy site.", source: "website" },
      personalBrand: { confidence: 0.92, evidence: "Own domain, podcast appearances, branded academy.", source: "website" },
      activity: { confidence: 0.88, evidence: "Weekly live sessions announced on Facebook and Instagram.", source: "facebook" },
    },
    contacts: { email: "carmen@delgadoacademy.es", website: "https://delgadoacademy.es", phone: "+34 6•• ••• •••" },
    status: "qualified",
    saved: true,
    hoursAgo: 6,
  },
  {
    id: "lead_lucia_fernandez",
    searchId: "srch_es_mihi",
    name: "Lucía Fernández",
    headline: "Skincare distributor · MIHI partner",
    company: "MIHI",
    location: { country: "Spain", city: "Bilbao" },
    languages: ["Spanish", "Basque"],
    platforms: [ig("lucia.skincare.bi", 9400), fb("lucia.fernandez.skin", 3400)],
    summary:
      "Lucía sells MIHI products locally with steady posting activity. No public evidence of a team beneath her, which caps the leadership component.",
    signals: {
      mlm: { confidence: 0.91, evidence: "\"Distribuidora oficial MIHI en Bizkaia\"", source: "facebook" },
      beauty: { confidence: 0.9, evidence: "Product photos and routines; MIHI catalogue links.", source: "instagram" },
      recruiting: { confidence: 0.44, evidence: "One mention: \"si te interesa el negocio, hablamos\".", source: "instagram" },
      location: { confidence: 1, evidence: "Bio: \"Bilbao · envíos a toda España\".", source: "instagram" },
      personalBrand: { confidence: 0.5, evidence: "Consistent posting, no independent brand assets.", source: "instagram" },
      activity: { confidence: 0.76, evidence: "9 posts in the last 30 days.", source: "instagram" },
    },
    status: "new",
    hoursAgo: 7,
  },
  {
    id: "lead_natalia_sokol",
    searchId: "srch_es_mihi",
    name: "Natalia Sokol",
    headline: "Network marketing mentor · beauty & wellness",
    location: { country: "Spain", city: "Málaga" },
    languages: ["Russian", "Ukrainian", "Spanish", "English"],
    platforms: [ig("natalia.sokol.mentor", 42100), th("natalia.sokol", 5100), blog("sokol-mentor.com")],
    summary:
      "Natalia mentors Russian- and Ukrainian-speaking beauty entrepreneurs from Málaga. Her blog documents team-building methodology, and recruiting webinars run monthly.",
    signals: {
      mlm: { confidence: 0.97, evidence: "\"12 лет в сетевом маркетинге, 3 компании\"", source: "blog" },
      beauty: { confidence: 0.82, evidence: "Focus split between beauty and wellness product lines.", source: "blog" },
      recruiting: { confidence: 0.95, evidence: "\"Вебинар для новых партнёров — каждый первый вторник\"", source: "instagram" },
      leadership: { confidence: 0.96, evidence: "\"Моя структура — 300+ партнёров в 5 странах\"", source: "blog" },
      location: { confidence: 0.9, evidence: "Bio: \"Málaga\"; blog mentions relocation to Spain in 2021.", source: "instagram" },
      personalBrand: { confidence: 0.95, evidence: "Own blog, paid mentorship program, 42k followers.", source: "blog" },
      activity: { confidence: 0.97, evidence: "Daily stories; 3 blog posts per month.", source: "instagram" },
    },
    contacts: { email: "hello@sokol-mentor.com", website: "https://sokol-mentor.com" },
    status: "contacted",
    saved: true,
    hoursAgo: 8,
  },
  {
    id: "lead_pilar_moreno",
    searchId: "srch_es_mihi",
    name: "Pilar Moreno",
    headline: "Cosmetics sales team lead",
    company: "Aurelle",
    location: { country: "Spain", city: "Zaragoza" },
    languages: ["Spanish"],
    platforms: [li("pilar-moreno-sales", 1800), ig("pilar.moreno.beauty", 6700)],
    summary:
      "Pilar leads a regional cosmetics sales team. Direct-sales background is clear; recruiting signals are limited to internal hiring language.",
    signals: {
      mlm: { confidence: 0.68, evidence: "\"Venta directa de cosmética desde 2016\" — model not explicitly MLM.", source: "linkedin" },
      beauty: { confidence: 0.93, evidence: "Role title: Cosmetics Sales Team Lead at Aurelle.", source: "linkedin" },
      recruiting: { confidence: 0.55, evidence: "\"Estamos ampliando el equipo comercial en Aragón\"", source: "linkedin" },
      leadership: { confidence: 0.85, evidence: "\"Responsable de 12 comerciales\"", source: "linkedin" },
      location: { confidence: 1, evidence: "LinkedIn location: Zaragoza, Aragon, Spain.", source: "linkedin" },
      personalBrand: { confidence: 0.35, evidence: "No personal site; low posting cadence.", source: "linkedin" },
      activity: { confidence: 0.5, evidence: "4 posts in the last 30 days.", source: "linkedin" },
    },
    contacts: { email: "p.moreno@aurelle-es.com" },
    status: "new",
    hoursAgo: 9,
  },
  {
    id: "lead_oksana_hrytsenko",
    searchId: "srch_es_mihi",
    name: "Oksana Hrytsenko",
    headline: "Beauty entrepreneur · team builder",
    location: { country: "Spain", city: "Alicante" },
    languages: ["Ukrainian", "Russian", "Spanish"],
    platforms: [ig("oksana.beauty.team", 15600), fb("oksana.hrytsenko.beauty", 4200), th("oksana.beauty", 900)],
    summary:
      "Oksana builds a Ukrainian-speaking beauty team on the Costa Blanca. Recruiting posts are frequent and explicit; leadership evidence is emerging rather than established.",
    signals: {
      mlm: { confidence: 0.9, evidence: "\"Партнер бренду, будую свою команду\"", source: "instagram" },
      beauty: { confidence: 0.92, evidence: "Skincare demos and product hauls dominate the feed.", source: "instagram" },
      recruiting: { confidence: 0.91, evidence: "\"Шукаю 5 дівчат у команду — навчання безкоштовне\"", source: "facebook" },
      leadership: { confidence: 0.62, evidence: "\"Моя міні-команда — 8 людей\"", source: "instagram" },
      location: { confidence: 0.95, evidence: "Bio: \"Alicante, España\".", source: "instagram" },
      personalBrand: { confidence: 0.66, evidence: "Recognisable visual style; no own domain.", source: "instagram" },
      activity: { confidence: 0.9, evidence: "Posts 4–5 times per week.", source: "instagram" },
    },
    status: "reviewed",
    hoursAgo: 11,
  },
  {
    id: "lead_sofia_marin",
    searchId: "srch_es_mihi",
    name: "Sofía Marín",
    headline: "Esthetician · salon owner",
    company: "Estudio Marín",
    location: { country: "Spain", city: "Murcia" },
    languages: ["Spanish"],
    platforms: [ig("estudiomarin", 5300), site("estudiomarin.es")],
    summary:
      "Sofía owns a beauty studio and retails cosmetics on site. She matches the beauty criterion strongly but shows no network-marketing or recruiting behaviour — likely a customer profile rather than a partner.",
    signals: {
      beauty: { confidence: 0.98, evidence: "Salon services and retail listed on estudiomarin.es.", source: "website" },
      location: { confidence: 1, evidence: "Studio address in Murcia.", source: "website" },
      personalBrand: { confidence: 0.42, evidence: "Salon brand rather than personal brand.", source: "website" },
      activity: { confidence: 0.55, evidence: "6 posts in the last 30 days.", source: "instagram" },
    },
    contacts: { email: "hola@estudiomarin.es", website: "https://estudiomarin.es" },
    status: "rejected",
    hoursAgo: 12,
  },
  {
    id: "lead_beatriz_lopes",
    searchId: "srch_es_mihi",
    name: "Beatriz Lopes",
    headline: "Cross-border beauty distributor (ES/PT)",
    location: { country: "Spain", city: "Vigo", region: "Galicia" },
    languages: ["Portuguese", "Spanish", "English"],
    platforms: [ig("bea.lopes.beauty", 13900), li("beatriz-lopes-distrib", 2200)],
    summary:
      "Beatriz operates across the Spain–Portugal border with a two-country distributor structure. Consistent recruiting cadence and a small but real team.",
    signals: {
      mlm: { confidence: 0.94, evidence: "\"Distribuidora em Espanha e Portugal — negócio de recomendação\"", source: "linkedin" },
      beauty: { confidence: 0.88, evidence: "Cosmetics catalogue links in bio and posts.", source: "instagram" },
      recruiting: { confidence: 0.83, evidence: "\"Procuro parceiras para a equipa da Galiza\"", source: "instagram" },
      leadership: { confidence: 0.7, evidence: "\"A minha equipa tem 15 consultoras\"", source: "linkedin" },
      location: { confidence: 0.92, evidence: "LinkedIn location: Vigo, Galicia, Spain.", source: "linkedin" },
      personalBrand: { confidence: 0.55, evidence: "Active on two platforms, no personal domain.", source: "instagram" },
      activity: { confidence: 0.8, evidence: "3–4 posts per week.", source: "instagram" },
    },
    contacts: { email: "beatriz.lopes.dist@gmail.com" },
    status: "new",
    hoursAgo: 13,
  },
  {
    id: "lead_ines_ferrer",
    searchId: "srch_es_mihi",
    name: "Inés Ferrer",
    headline: "Wellness & beauty network partner",
    location: { country: "Spain", city: "Palma" },
    languages: ["Spanish", "German", "English"],
    platforms: [ig("ines.wellness.pm", 7800), fb("ines.ferrer.wellness", 2100)],
    summary:
      "Inés serves the German-speaking community in Mallorca with a wellness-leaning product mix. Beauty relevance is partial; recruiting is active.",
    signals: {
      mlm: { confidence: 0.87, evidence: "\"Selbstständige Partnerin — Empfehlungsmarketing\"", source: "facebook" },
      beauty: { confidence: 0.61, evidence: "Mix of supplements and skincare; beauty is roughly a third of posts.", source: "instagram" },
      recruiting: { confidence: 0.8, evidence: "\"Ich suche Partnerinnen auf Mallorca\"", source: "facebook" },
      leadership: { confidence: 0.5, evidence: "\"Mein kleines Team wächst\"", source: "facebook" },
      location: { confidence: 0.9, evidence: "Bio: \"Mallorca\".", source: "instagram" },
      personalBrand: { confidence: 0.45, evidence: "Moderate reach, no own domain.", source: "instagram" },
      activity: { confidence: 0.72, evidence: "Weekly posts plus regular stories.", source: "instagram" },
    },
    status: "contact_later",
    hoursAgo: 15,
  },
  {
    id: "lead_rocio_navarro",
    searchId: "srch_es_mihi",
    name: "Rocío Navarro",
    headline: "Beauty affiliate & micro-influencer",
    location: { country: "Spain", city: "Granada" },
    languages: ["Spanish"],
    platforms: [ig("rocio.navarro.glow", 4100)],
    summary:
      "Rocío promotes cosmetics through affiliate links. No network structure or recruiting evidence — closer to an affiliate creator than a network partner.",
    signals: {
      mlm: { confidence: 0.38, evidence: "Affiliate discount codes only; no partner language.", source: "instagram" },
      beauty: { confidence: 0.9, evidence: "Makeup and skincare content throughout.", source: "instagram" },
      location: { confidence: 1, evidence: "Bio: \"Granada\".", source: "instagram" },
      personalBrand: { confidence: 0.5, evidence: "Small but consistent creator presence.", source: "instagram" },
      activity: { confidence: 0.7, evidence: "8 posts in the last 30 days.", source: "instagram" },
    },
    status: "new",
    hoursAgo: 16,
  },

  /* ----------------------------------------------------------- Germany ---- */
  {
    id: "lead_katrin_mueller",
    searchId: "srch_de_mihi",
    name: "Katrin Müller",
    headline: "Teamleiterin · Beauty & Empfehlungsmarketing",
    company: "MIHI",
    location: { country: "Germany", city: "Munich", region: "Bavaria" },
    languages: ["German", "English"],
    platforms: [ig("katrin.beautyteam", 21700), li("katrin-mueller-beauty", 2900), site("katrin-mueller.de")],
    summary:
      "Katrin leads a MIHI distributor team in southern Germany and publishes a structured onboarding path on her own site. Strong across every scored signal.",
    signals: {
      mlm: { confidence: 0.97, evidence: "\"Seit 2017 im Empfehlungsmarketing, Team in DACH\"", source: "website" },
      beauty: { confidence: 0.93, evidence: "\"Naturkosmetik & Hautpflege\" product focus.", source: "website" },
      recruiting: { confidence: 0.92, evidence: "\"Bewirb dich für mein Team — Onboarding startet monatlich\"", source: "website" },
      leadership: { confidence: 0.93, evidence: "\"Ich begleite 60+ Partnerinnen\"", source: "instagram" },
      location: { confidence: 1, evidence: "Impressum lists a Munich address.", source: "website" },
      personalBrand: { confidence: 0.88, evidence: "Own domain with press section and podcast.", source: "website" },
      activity: { confidence: 0.9, evidence: "Posts 5 times per week.", source: "instagram" },
    },
    contacts: { email: "team@katrin-mueller.de", website: "https://katrin-mueller.de" },
    status: "qualified",
    saved: true,
    hoursAgo: 26,
  },
  {
    id: "lead_janina_weber",
    searchId: "srch_de_mihi",
    name: "Janina Weber",
    headline: "Selbstständige Kosmetikberaterin",
    location: { country: "Germany", city: "Hamburg" },
    languages: ["German"],
    platforms: [ig("janina.kosmetik.hh", 8600), fb("janina.weber.kosmetik", 2800)],
    summary:
      "Janina consults on cosmetics independently in Hamburg with visible partner recruiting, but no evidence of a team she leads.",
    signals: {
      mlm: { confidence: 0.89, evidence: "\"Unabhängige Beraterin — Empfehlungsmarketing\"", source: "facebook" },
      beauty: { confidence: 0.94, evidence: "Skincare consultations advertised in every post.", source: "instagram" },
      recruiting: { confidence: 0.76, evidence: "\"Du willst mitmachen? Schreib mir 'TEAM'\"", source: "instagram" },
      location: { confidence: 1, evidence: "Bio: \"Hamburg\".", source: "instagram" },
      personalBrand: { confidence: 0.48, evidence: "Consistent template design, no own domain.", source: "instagram" },
      activity: { confidence: 0.78, evidence: "12 posts in the last 30 days.", source: "instagram" },
    },
    status: "new",
    hoursAgo: 28,
  },
  {
    id: "lead_svetlana_richter",
    searchId: "srch_de_mihi",
    name: "Svetlana Richter",
    headline: "Netzwerk-Mentorin · Beauty-Business",
    location: { country: "Germany", city: "Cologne" },
    languages: ["Russian", "German", "English"],
    platforms: [ig("svetlana.mentor.beauty", 33400), th("svetlana.mentor", 3800), blog("beautybusiness-mentor.de")],
    summary:
      "Svetlana mentors Russian-speaking beauty entrepreneurs across Germany. Her blog details duplication systems and she runs recurring recruiting webinars.",
    signals: {
      mlm: { confidence: 0.96, evidence: "\"9 лет в индустрии сетевого маркетинга\"", source: "blog" },
      beauty: { confidence: 0.86, evidence: "Beauty-business niche stated in the blog header.", source: "blog" },
      recruiting: { confidence: 0.93, evidence: "\"Набор в команду открыт — старт 1 числа\"", source: "instagram" },
      leadership: { confidence: 0.91, evidence: "\"Структура 180+ партнёров в DACH\"", source: "blog" },
      location: { confidence: 0.95, evidence: "Blog imprint lists Cologne.", source: "blog" },
      personalBrand: { confidence: 0.93, evidence: "Own blog, paid course, large following.", source: "blog" },
      activity: { confidence: 0.94, evidence: "Daily stories and weekly blog posts.", source: "instagram" },
    },
    contacts: { email: "info@beautybusiness-mentor.de", website: "https://beautybusiness-mentor.de" },
    status: "reviewed",
    saved: true,
    hoursAgo: 30,
  },
  {
    id: "lead_miriam_schulz",
    searchId: "srch_de_mihi",
    name: "Miriam Schulz",
    headline: "Vertriebsleiterin Kosmetik",
    company: "Lumea",
    location: { country: "Germany", city: "Berlin" },
    languages: ["German", "English"],
    platforms: [li("miriam-schulz-vertrieb", 4300)],
    summary:
      "Miriam manages a classic cosmetics sales organisation. Leadership is strong, but the business model appears to be traditional distribution rather than network marketing.",
    signals: {
      mlm: { confidence: 0.35, evidence: "No referral or partner language; classic B2B distribution.", source: "linkedin" },
      beauty: { confidence: 0.95, evidence: "Title: Vertriebsleiterin Kosmetik at Lumea.", source: "linkedin" },
      recruiting: { confidence: 0.4, evidence: "Corporate job postings for sales reps.", source: "linkedin" },
      leadership: { confidence: 0.9, evidence: "\"Verantwortlich für 25 Mitarbeitende\"", source: "linkedin" },
      location: { confidence: 1, evidence: "LinkedIn location: Berlin, Germany.", source: "linkedin" },
      activity: { confidence: 0.45, evidence: "3 posts in the last 30 days.", source: "linkedin" },
    },
    contacts: { email: "m.schulz@lumea.de" },
    status: "contact_later",
    hoursAgo: 31,
  },
  {
    id: "lead_daniela_krause",
    searchId: "srch_de_mihi",
    name: "Daniela Krause",
    headline: "Beauty-Partnerin & Content Creator",
    location: { country: "Germany", city: "Stuttgart" },
    languages: ["German"],
    platforms: [ig("dani.beautypartner", 12400), th("dani.beautypartner", 1400)],
    summary:
      "Daniela combines creator content with partner sales. Recruiting language appears in stories rather than permanent posts, so confidence is moderate.",
    signals: {
      mlm: { confidence: 0.84, evidence: "\"Partnerin\" plus a personal referral shop link in bio.", source: "instagram" },
      beauty: { confidence: 0.95, evidence: "Skincare routines, before/after content.", source: "instagram" },
      recruiting: { confidence: 0.67, evidence: "Story highlight titled \"TEAM\" with a signup link.", source: "instagram" },
      leadership: { confidence: 0.4, evidence: "\"Erste eigene Partnerin an Board 🎉\"", source: "instagram" },
      location: { confidence: 1, evidence: "Bio: \"Stuttgart\".", source: "instagram" },
      personalBrand: { confidence: 0.7, evidence: "Distinct creator identity, brand deals.", source: "instagram" },
      activity: { confidence: 0.92, evidence: "Near-daily posting.", source: "instagram" },
    },
    status: "new",
    hoursAgo: 33,
  },
  {
    id: "lead_yuliya_hoffmann",
    searchId: "srch_de_mihi",
    name: "Yuliya Hoffmann",
    headline: "Team leader · beauty & skincare network",
    location: { country: "Germany", city: "Frankfurt" },
    languages: ["Ukrainian", "Russian", "German"],
    platforms: [ig("yuliya.beauty.team", 19800), fb("yuliya.hoffmann.beauty", 6100), site("yuliya-team.de")],
    summary:
      "Yuliya leads a Ukrainian-speaking beauty team in the Rhine-Main region with a documented onboarding funnel on her own site.",
    signals: {
      mlm: { confidence: 0.95, evidence: "\"Наша команда — партнери бренду з 2019 року\"", source: "website" },
      beauty: { confidence: 0.91, evidence: "Skincare product line presented on the site.", source: "website" },
      recruiting: { confidence: 0.89, evidence: "\"Заповни анкету — співбесіда протягом 48 годин\"", source: "website" },
      leadership: { confidence: 0.88, evidence: "\"35 партнерів у моїй структурі\"", source: "instagram" },
      location: { confidence: 0.96, evidence: "Site lists Frankfurt am Main.", source: "website" },
      personalBrand: { confidence: 0.72, evidence: "Own domain and consistent identity across platforms.", source: "website" },
      activity: { confidence: 0.86, evidence: "4 posts per week plus daily stories.", source: "instagram" },
    },
    contacts: { email: "team@yuliya-team.de", website: "https://yuliya-team.de" },
    status: "reviewed",
    hoursAgo: 35,
  },
  {
    id: "lead_sabine_lang",
    searchId: "srch_de_mihi",
    name: "Sabine Lang",
    headline: "Kosmetikstudio-Inhaberin",
    company: "Studio Lang",
    location: { country: "Germany", city: "Nuremberg" },
    languages: ["German"],
    platforms: [site("studio-lang-kosmetik.de"), fb("studio.lang.kosmetik", 1900)],
    summary:
      "Sabine owns a cosmetics studio. Beauty match is unambiguous, network marketing signals are absent — kept for completeness rather than outreach.",
    signals: {
      beauty: { confidence: 0.97, evidence: "Treatment menu published on the studio site.", source: "website" },
      location: { confidence: 1, evidence: "Studio address in Nuremberg.", source: "website" },
      activity: { confidence: 0.4, evidence: "Occasional Facebook updates.", source: "facebook" },
    },
    contacts: { email: "kontakt@studio-lang-kosmetik.de", website: "https://studio-lang-kosmetik.de" },
    status: "rejected",
    hoursAgo: 37,
  },

  /* ------------------------------------------------------------- Italy ---- */
  {
    id: "lead_giulia_conti",
    searchId: "srch_it_beauty",
    name: "Giulia Conti",
    headline: "Beauty network leader · Milano",
    company: "Velair",
    location: { country: "Italy", city: "Milan", region: "Lombardy" },
    languages: ["Italian", "English"],
    platforms: [ig("giulia.beautynetwork", 27600), li("giulia-conti-beauty", 3600), site("giuliaconti.it")],
    summary:
      "Giulia leads a beauty distribution network from Milan and runs a public mentorship track for new partners.",
    signals: {
      mlm: { confidence: 0.95, evidence: "\"Network marketing nel settore beauty dal 2016\"", source: "website" },
      beauty: { confidence: 0.94, evidence: "Skincare and cosmetics catalogue on her site.", source: "website" },
      recruiting: { confidence: 0.9, evidence: "\"Cerco 4 nuove collaboratrici per il team di Milano\"", source: "instagram" },
      leadership: { confidence: 0.92, evidence: "\"Coordino un team di 50 persone\"", source: "linkedin" },
      location: { confidence: 1, evidence: "Site footer lists Milano.", source: "website" },
      personalBrand: { confidence: 0.86, evidence: "Own domain, event speaking, newsletter.", source: "website" },
      activity: { confidence: 0.89, evidence: "5 posts per week.", source: "instagram" },
    },
    contacts: { email: "ciao@giuliaconti.it", website: "https://giuliaconti.it" },
    status: "qualified",
    saved: true,
    hoursAgo: 74,
  },
  {
    id: "lead_francesca_bruno",
    searchId: "srch_it_beauty",
    name: "Francesca Bruno",
    headline: "Consulente beauty indipendente",
    location: { country: "Italy", city: "Rome" },
    languages: ["Italian"],
    platforms: [ig("francesca.beauty.rm", 10200), fb("francesca.bruno.beauty", 3300)],
    summary:
      "Francesca consults independently in Rome. Recruiting appears occasionally; no team evidence found in public sources.",
    signals: {
      mlm: { confidence: 0.85, evidence: "\"Consulente indipendente\" with referral shop link.", source: "instagram" },
      beauty: { confidence: 0.92, evidence: "Beauty routines and product reviews.", source: "instagram" },
      recruiting: { confidence: 0.6, evidence: "\"Vuoi lavorare con me? Scrivimi\"", source: "facebook" },
      location: { confidence: 1, evidence: "Bio: \"Roma\".", source: "instagram" },
      personalBrand: { confidence: 0.5, evidence: "Steady presence on two platforms.", source: "instagram" },
      activity: { confidence: 0.74, evidence: "10 posts in the last 30 days.", source: "instagram" },
    },
    status: "new",
    hoursAgo: 76,
  },
  {
    id: "lead_valentina_greco",
    searchId: "srch_it_beauty",
    name: "Valentina Greco",
    headline: "Founder · skincare brand & partner network",
    company: "Greco Skin",
    location: { country: "Italy", city: "Naples" },
    languages: ["Italian", "English", "Spanish"],
    platforms: [ig("valentina.grecoskin", 38900), li("valentina-greco-skin", 5200), site("grecoskin.it")],
    summary:
      "Valentina founded a skincare brand distributed through a partner network across southern Italy. Recruiting and leadership are both documented publicly.",
    signals: {
      mlm: { confidence: 0.9, evidence: "\"Rete di partner indipendenti in tutto il Sud Italia\"", source: "website" },
      beauty: { confidence: 0.98, evidence: "Owns a skincare brand.", source: "website" },
      recruiting: { confidence: 0.87, evidence: "\"Diventa partner Greco Skin — candidature aperte\"", source: "website" },
      leadership: { confidence: 0.9, evidence: "\"Il nostro network conta 120 partner\"", source: "linkedin" },
      location: { confidence: 1, evidence: "Company registered in Naples.", source: "website" },
      personalBrand: { confidence: 0.94, evidence: "Founder brand with press coverage.", source: "website" },
      activity: { confidence: 0.85, evidence: "4 posts per week.", source: "instagram" },
    },
    contacts: { email: "partner@grecoskin.it", website: "https://grecoskin.it" },
    status: "reviewed",
    saved: true,
    hoursAgo: 78,
  },
  {
    id: "lead_chiara_marino",
    searchId: "srch_it_beauty",
    name: "Chiara Marino",
    headline: "Beauty coach & team mentor",
    location: { country: "Italy", city: "Turin" },
    languages: ["Italian", "French"],
    platforms: [ig("chiara.beautycoach", 16800), th("chiara.beautycoach", 2100), blog("chiaramarino.blog")],
    summary:
      "Chiara coaches beauty consultants and documents duplication tactics on her blog. Mid-sized team, high content cadence.",
    signals: {
      mlm: { confidence: 0.92, evidence: "\"Il mio business è network marketing, non vendita diretta classica\"", source: "blog" },
      beauty: { confidence: 0.89, evidence: "Beauty coaching niche stated throughout the blog.", source: "blog" },
      recruiting: { confidence: 0.84, evidence: "\"Prossimo start del team: lunedì\"", source: "instagram" },
      leadership: { confidence: 0.8, evidence: "\"Seguo 22 consulenti\"", source: "blog" },
      location: { confidence: 0.95, evidence: "Blog about page: Torino.", source: "blog" },
      personalBrand: { confidence: 0.83, evidence: "Own blog and coaching offer.", source: "blog" },
      activity: { confidence: 0.91, evidence: "Daily stories, weekly posts.", source: "instagram" },
    },
    contacts: { email: "info@chiaramarino.blog", website: "https://chiaramarino.blog" },
    status: "new",
    hoursAgo: 80,
  },
  {
    id: "lead_alessia_ferrari",
    searchId: "srch_it_beauty",
    name: "Alessia Ferrari",
    headline: "Wellness distributor · Bologna",
    location: { country: "Italy", city: "Bologna" },
    languages: ["Italian"],
    platforms: [fb("alessia.ferrari.wellness", 5400), ig("alessia.wellness.bo", 6200)],
    summary:
      "Alessia distributes wellness products with a limited beauty overlap. Recruiting is active in Facebook groups.",
    signals: {
      mlm: { confidence: 0.88, evidence: "\"Incaricata alle vendite — team in crescita\"", source: "facebook" },
      beauty: { confidence: 0.45, evidence: "Mostly supplements; occasional skincare posts.", source: "instagram" },
      recruiting: { confidence: 0.82, evidence: "\"Cerco persone motivate per il mio team\"", source: "facebook" },
      leadership: { confidence: 0.55, evidence: "\"Il mio team è arrivato a 11 persone\"", source: "facebook" },
      location: { confidence: 1, evidence: "Bio: \"Bologna\".", source: "instagram" },
      personalBrand: { confidence: 0.4, evidence: "Group-driven presence, no own site.", source: "facebook" },
      activity: { confidence: 0.68, evidence: "Weekly posts in two groups.", source: "facebook" },
    },
    status: "new",
    hoursAgo: 82,
  },
];

/* -------------------------------------------------------------- assembling */

function buildSignals(seed: LeadSeed): LeadSignal[] {
  const order: SignalType[] = [
    "mlm",
    "beauty",
    "recruiting",
    "leadership",
    "location",
    "personalBrand",
    "activity",
  ];

  return order.map((type) => {
    const detail = seed.signals[type];
    if (!detail) {
      return { type, detected: false, confidence: 0 };
    }
    const platform = detail.source;
    const platformEntry = seed.platforms.find((entry) => entry.platform === platform);
    return {
      type,
      detected: detail.confidence >= 0.5,
      confidence: Number(detail.confidence.toFixed(2)),
      evidence: detail.evidence,
      sourceUrl: platformEntry?.url,
      sourcePlatform: platform,
    };
  });
}

function buildSources(seed: LeadSeed): LeadSource[] {
  if (seed.sources) {
    return seed.sources.map((source, index) => ({
      id: `${seed.id}_src_${index}`,
      discoveredAt: isoHoursAgo(seed.hoursAgo + 1),
      ...source,
    }));
  }

  return seed.platforms.map((entry, index) => ({
    id: `${seed.id}_src_${index}`,
    platform: entry.platform,
    url: entry.url,
    title: sourceTitle(seed, entry.platform),
    snippet: sourceSnippet(seed, entry.platform),
    discoveredAt: isoHoursAgo(seed.hoursAgo + 1),
  }));
}

function sourceTitle(seed: LeadSeed, platform: Platform) {
  switch (platform) {
    case "instagram":
      return `${seed.name} (@${seed.platforms.find((p) => p.platform === "instagram")?.handle?.replace("@", "")}) · Instagram`;
    case "linkedin":
      return `${seed.name} — ${seed.headline} | LinkedIn`;
    case "facebook":
      return `${seed.name} | Facebook`;
    case "threads":
      return `${seed.name} · Threads`;
    case "blog":
      return `${seed.name} — blog`;
    default:
      return `${seed.company ?? seed.name} — official site`;
  }
}

function sourceSnippet(seed: LeadSeed, platform: Platform) {
  const city = seed.location.city ?? seed.location.country ?? "";
  switch (platform) {
    case "instagram":
      return `${seed.headline} · ${city}. Public profile discovered through web search.`;
    case "linkedin":
      return `Public profile: ${seed.headline}. ${city}.`;
    case "facebook":
      return `Public page mentioning ${seed.headline.toLowerCase()} in ${city}.`;
    case "threads":
      return `Public Threads profile cross-linked from Instagram.`;
    case "blog":
      return `Personal blog covering team building and product content.`;
    default:
      return `Company or personal website listing contact details and team information.`;
  }
}

export const MOCK_LEADS: Lead[] = SEEDS.map((seed) => {
  const signals = buildSignals(seed);
  const { score, breakdown } = computeScore(signals, DEFAULT_SIGNAL_WEIGHTS);
  const createdAt = isoHoursAgo(seed.hoursAgo);

  return {
    id: seed.id,
    searchId: seed.searchId,
    searchName: SEARCH_NAMES[seed.searchId] ?? "Search",
    name: seed.name,
    headline: seed.headline,
    company: seed.company,
    location: seed.location,
    languages: seed.languages,
    score,
    scoreBreakdown: breakdown,
    platforms: seed.platforms,
    summary: seed.summary,
    signals,
    sources: buildSources(seed),
    contacts: seed.contacts ?? {},
    status: seed.status ?? "new",
    saved: seed.saved ?? false,
    archived: false,
    notes:
      seed.status === "contacted"
        ? [
            {
              id: `${seed.id}_note_1`,
              body: "Sent a first message in Russian — mentioned her webinar cadence. Waiting for a reply.",
              author: "You",
              createdAt: isoHoursAgo(Math.max(1, seed.hoursAgo - 2)),
            },
          ]
        : [],
    createdAt,
  };
}).sort((a, b) => b.score - a.score);

export const MOCK_LEADS_BY_SEARCH = MOCK_LEADS.reduce<Record<string, Lead[]>>((acc, lead) => {
  (acc[lead.searchId] ??= []).push(lead);
  return acc;
}, {});
