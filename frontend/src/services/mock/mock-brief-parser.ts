/**
 * The offline twin of `POST /searches/parse`, for the demo with no backend.
 *
 * It mirrors the backend's *rule* reader, not the model: countries, languages,
 * well-known brands and a lead count are recognised, and everything else is left
 * empty for the review screen to ask about. That is the honest behaviour for a
 * reader without judgement — a guessed field looks exactly like an answered one.
 */

import {
  balanceRequirements,
  COUNTRIES,
  DEFAULT_TARGET_LEADS,
  emptyCriteria,
  LANGUAGES,
} from "@/lib/domain";
import type { ParsedBrief } from "@/services/types";

const LANGUAGE_STEMS: Record<string, string[]> = {
  uk: ["українськ", "украинск", "ukrainian", "україно", "украино"],
  ru: ["російськ", "русск", "russian", "русскоязычн", "русскоговорящ"],
  en: ["англійськ", "английск", "english"],
  es: ["іспанськ", "испанск", "spanish", "español"],
  pl: ["польськ", "польск", "polish"],
  de: ["німецьк", "немецк", "german", "deutsch"],
  it: ["італійськ", "итальянск", "italian"],
  pt: ["португальськ", "португальск", "portuguese"],
  fr: ["французьк", "французск", "french"],
  ro: ["румунськ", "румынск", "romanian"],
  cs: ["чеськ", "чешск", "czech"],
  nl: ["нідерландськ", "голландськ", "голландск", "dutch"],
};

/** Country stems, matched at the start of a word; Slavic languages inflect places. */
const COUNTRY_STEMS: Record<string, string[]> = {
  UA: ["україн", "украин", "ukrain"],
  ES: ["іспані", "испани", "spain", "españa"],
  PL: ["польщ", "польш", "poland", "polska"],
  DE: ["німеччин", "германи", "germany", "deutschland"],
  IT: ["італі", "итали", "italy", "italia"],
  PT: ["португалі", "португали", "portugal"],
  FR: ["франці", "франци", "france"],
  NL: ["нідерланд", "голланд", "netherlands"],
  CZ: ["чехі", "чехи", "czech"],
  AT: ["австрі", "австри", "austria"],
  CH: ["швейцарі", "швейцари", "switzerland"],
  GB: ["великобритані", "britain"],
  RO: ["румуні", "румыни", "romania"],
  BE: ["бельгі", "belgium"],
  US: ["сша", "usa"],
};

const BRANDS: Record<string, string[]> = {
  Farmasi: ["farmasi", "фармасі", "фармаси"],
  Jerelia: ["jerelia", "джерелія", "джерелия"],
  Oriflame: ["oriflame", "оріфлейм", "орифлейм"],
  Avon: ["avon", "ейвон", "эйвон"],
  Faberlic: ["faberlic", "фаберлік", "фаберлик"],
  Amway: ["amway", "амвей"],
  "Mary Kay": ["mary kay", "мері кей"],
  Herbalife: ["herbalife", "гербалайф"],
  Atomy: ["atomy", "атомі", "атоми"],
  Greenway: ["greenway", "грінвей", "гринвей"],
  MIHI: ["mihi"],
};

const LEAD_COUNT =
  /(\d{1,4})\s*(?:лід|лид|lead|кандидат|candidate|людей|люд|осіб|особ|контакт|профіл|профил)/i;

export function parseBriefOffline(text: string): ParsedBrief {
  const brief = text.trim().slice(0, 4000);
  const lowered = brief.toLowerCase();
  const words = lowered.match(/[\p{L}\p{N}'’]+/gu) ?? [];

  const languageCodes = Object.entries(LANGUAGE_STEMS)
    .filter(([, stems]) => stems.some((stem) => lowered.includes(stem)))
    .map(([code]) => code);
  // "українською" names a language, not Ukraine.
  const placeWords = words.filter(
    (word) => !Object.values(LANGUAGE_STEMS).flat().some((stem) => word.includes(stem)),
  );
  const countryCode = Object.entries(COUNTRY_STEMS).find(([, stems]) =>
    placeWords.some((word) => stems.some((stem) => word.startsWith(stem))),
  )?.[0];

  const brands: string[] = [];
  for (const [canonical, spellings] of Object.entries(BRANDS)) {
    const found = spellings.filter((spelling) => lowered.includes(spelling));
    for (const brand of found.length ? [...found, canonical] : []) {
      if (!brands.some((entry) => entry.toLowerCase() === brand.toLowerCase())) {
        brands.push(brand);
      }
    }
  }

  const count = LEAD_COUNT.exec(brief);
  const firstSentence = brief.split(/[.!?\n]/)[0] ?? brief;

  return {
    name: firstSentence.length > 60 ? `${firstSentence.slice(0, 57)}…` : firstSentence,
    parser: "rules",
    criteria: {
      ...emptyCriteria(),
      brief,
      brands,
      location: {
        country: COUNTRIES.find((entry) => entry.id === countryCode)?.token,
      },
      languages: LANGUAGES.filter((entry) => languageCodes.includes(entry.id)).map(
        (entry) => entry.token,
      ),
      // Nothing about the niche is assumed: the product recruits for any role. The
      // brands found are the one thing to judge by; the review asks for the rest.
      mustHave: [],
      niceToHave: [],
      requirements: balanceRequirements([
        ...(brands.length
          ? [{ id: "r1", label: brands[0], terms: brands, importance: "high" as const, weight: 0 }]
          : []),
        ...(countryCode ? [{ id: "location", importance: "normal" as const, weight: 0 }] : []),
      ]),
      targetLeads: count ? Math.min(1000, Number(count[1])) : DEFAULT_TARGET_LEADS,
    },
  };
}
