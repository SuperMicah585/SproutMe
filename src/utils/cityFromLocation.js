const CITY_ALIASES = {
  sf: 'san francisco',
  'san fran': 'san francisco',
  'san francisco': 'san francisco',
  la: 'los angeles',
  'los angeles': 'los angeles',
  nyc: 'new york',
  'new york city': 'new york',
  'new york': 'new york',
  brooklyn: 'brooklyn',
  dc: 'washington',
  'washington dc': 'washington',
  washington: 'washington',
  pdx: 'portland',
  portland: 'portland',
  chi: 'chicago',
  chicago: 'chicago',
  philly: 'philadelphia',
  philadelphia: 'philadelphia',
};

const SEATTLE_METRO = new Set([
  'bellevue',
  'kirkland',
  'redmond',
  'shoreline',
  'renton',
  'tukwila',
  'seatac',
  'sea tac',
  'burien',
  'mercer island',
  'issaquah',
  'sammamish',
  'bothell',
  'kenmore',
  'woodinville',
  'lynnwood',
  'edmonds',
  'newcastle',
  'kent',
  'des moines',
  'mill creek',
  'mukilteo',
  'lake forest park',
  'mountlake terrace',
]);

const METRO_PARENT = {
  ...Object.fromEntries([...SEATTLE_METRO].map((city) => [city, 'seattle'])),
};

export const normalizePlace = (value) =>
  String(value || '')
    .toLowerCase()
    .replace(/[./]/g, ' ')
    .replace(/[^a-z0-9\s]/g, '')
    .replace(/\s+/g, ' ')
    .trim();

const canonicalCity = (value) => {
  const normalized = normalizePlace(value);
  if (!normalized) return '';
  if (CITY_ALIASES[normalized]) return CITY_ALIASES[normalized];
  const withoutState = normalized.replace(/\b[a-z]{2}$/, '').trim();
  return CITY_ALIASES[withoutState] || CITY_ALIASES[normalized] || withoutState || normalized;
};

const hasToken = (haystack, token) => {
  if (!token) return false;
  if (token.length <= 2) return new RegExp(`\\b${token}\\b`).test(haystack);
  return haystack.includes(token);
};

const metroParentFor = (city, regionCode) => {
  const parent = METRO_PARENT[city];
  if (!parent) return null;
  if (city === 'redmond' && regionCode === 'or') return null;
  return parent;
};

export const collectVenueCities = (events) => {
  const cities = new Set();
  (events || []).forEach((event) => {
    const match = String(event?.venue || '').match(/\(([^)]+)\)/);
    if (match?.[1]) cities.add(match[1].trim());
  });
  return [...cities];
};

export const matchEventCity = (geo, venueCities) => {
  if (!geo?.city || !venueCities?.length) return null;
  const region = normalizePlace(geo.region);
  const regionCode = normalizePlace(geo.regionCode);
  const city = canonicalCity(geo.city);
  const searchCities = [city, metroParentFor(city, regionCode)].filter(Boolean);
  if (!searchCities.length) return null;

  let best = null;
  venueCities.forEach((option) => {
    const optionNorm = normalizePlace(option);
    const optionCanon = canonicalCity(option);
    searchCities.forEach((searchCity, index) => {
      const metroBoost = index === 0 ? 0 : -8;
      let score = 0;
      const cityAndRegion = hasToken(optionNorm, searchCity)
        && (hasToken(optionNorm, regionCode) || hasToken(optionNorm, region));
      if (cityAndRegion) score = 120;
      else if (optionNorm.startsWith(`${searchCity} `)) score = 100;
      else if (optionCanon === searchCity || optionNorm === searchCity) score = 80;
      else if (hasToken(optionNorm, searchCity) || optionCanon.includes(searchCity)) score = 60;
      if (hasToken(optionNorm, regionCode)) score += 8;
      if (hasToken(optionNorm, region)) score += 4;
      score += metroBoost;
      if (!best || score > best.score) best = { option, score };
    });
  });

  return best && best.score >= 60 ? best.option : null;
};

const fetchJson = async (url, timeoutMs = 2500) => {
  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetch(url, { signal: controller.signal });
    if (!response.ok) throw new Error('geo failed');
    return await response.json();
  } finally {
    window.clearTimeout(timer);
  }
};

export const lookupApproxLocation = async () => {
  const sources = [
    {
      url: 'https://get.geojs.io/v1/ip/geo.json',
      parse: (data) => ({ city: data.city, region: data.region, regionCode: data.region_code }),
    },
    {
      url: 'https://ipwho.is/',
      parse: (data) => (data.success === false
        ? null
        : { city: data.city, region: data.region, regionCode: data.region_code }),
    },
    {
      url: 'https://ipapi.co/json/',
      parse: (data) => (data.error
        ? null
        : { city: data.city, region: data.region, regionCode: data.region_code }),
    },
  ];

  for (const source of sources) {
    try {
      const geo = source.parse(await fetchJson(source.url));
      if (geo?.city) return geo;
    } catch {
      // try the next provider
    }
  }
  return null;
};
