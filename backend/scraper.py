"""Website crawler that uses Gemini Flash to extract companies from pages."""

import asyncio
import json
import os
import re
from dataclasses import dataclass
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup
import httpx

# Playwright for JS-rendered pages
_playwright_available = False
try:
    from playwright.async_api import async_playwright
    _playwright_available = True
except ImportError:
    pass

GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "")
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent"

PRIORITY_KEYWORDS = [
    "portfolio", "companies", "startups", "investments", "our-companies",
    "our-portfolio", "funded", "backed", "ventures",
    "directory", "listings", "projects",
    "alumni", "cohort", "batch", "showcase",
    "girisim", "yatirim", "sirket", "network",
]

PAGINATION_PATTERNS = [
    r"page[/-]?\d+", r"\?page=\d+", r"offset=\d+",
    r"load-more", r"next", r"older",
]

SKIP_KEYWORDS = [
    "login", "signup", "register", "cart", "checkout", "privacy",
    "terms", "cookie", "careers", "jobs", "press",
    "contact", "faq", "help", "support", "legal", "sitemap",
    "feed", "rss", ".pdf", ".jpg", ".png", ".gif", ".svg",
    "mailto:", "javascript:", "tel:", "#",
    "/partner", "/advisor", "/mentor",
    "twitter.com", "linkedin.com", "facebook.com", "instagram.com",
    "youtube.com", "github.com",
    "/iletisim",
]

RAISE_KEYWORDS_TR = [
    "yatırım arıyor", "yatırım arayan", "yatırım arıyoruz",
    "fonlama", "fon topluyor", "tur açtı", "seed turu", "pre-seed",
    "yatırımcı arıyor", "yatırım turu", "raising", "open round",
    "investor looking", "looking for investor", "fundraising",
    "seeking investment", "seeking funding", "open to investors",
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
}

# Blacklist: known non-startup entities that get falsely extracted
BLACKLIST_NAMES = {
    "openai", "anthropic", "google", "microsoft", "apple", "meta", "amazon",
    "facebook", "twitter", "linkedin", "instagram", "youtube", "github",
    "lyft", "uber", "airbnb", "stripe", "glassdoor", "slack",
    "techstars", "ycombinator", "y combinator", "500 startups", "500 global",
    "sequoia", "a16z", "andreessen horowitz", "accel", "benchmark",
    "seedtable", "crunchbase", "dealroom", "pitchbook",
    "harvard", "stanford", "mit", "oxford", "cambridge",
}

EXTRACT_PROMPT_PART1 = """You are a professional startup analyst extracting company data from a startup / VC / accelerator / pitch-platform website.

TASK: Extract ALL startup/tech companies mentioned on this page. For each, try to determine whether the company is ACTIVELY SEEKING INVESTMENT and, if so, how much.

For EACH company found, return:
- name: company name exactly as written (REQUIRED)
- description: 1-2 sentence English description of what the company does. If text is in Turkish or another language, TRANSLATE to English. Must explain the actual product/service.
- industry: ONE of: Fintech, AI, HealthTech, SaaS, E-commerce, Cybersecurity, EdTech, IoT, Gaming, Logistics, FoodTech, CleanTech, PropTech, InsurTech, HRTech, MarTech, Robotics, Biotech, DeepTech, Mobility, AgriTech, LegalTech, RegTech, Media, Entertainment, Travel, Fashion, Social, Analytics, DevTools, Infrastructure
- location: city and/or country (e.g. "Istanbul, Turkey")
- website: company URL if visible
- founded_year: founding year as integer, or null
- founders: array of founder full names (e.g. ["Ayşe Yılmaz", "Mehmet Demir"]). Include if mentioned anywhere on the page as founder / co-founder / CEO & founder / kurucu / kurucu ortak. Empty array if unknown.
- is_raising: true ONLY if there is EXPLICIT evidence the company is currently open to new investment. Signals: phrases like "raising", "open round", "seeking investment", "looking for investors", "pre-seed / seed / Series A open", "yatırım arıyor", "yatırım turu açık", "fon topluyor", "pitch deck", "invest now button", "active campaign", "round closes in X days". A company just HAVING past funding does NOT count. Set false if unclear.
- funding_stage: one of "Pre-seed", "Seed", "Series A", "Series B", "Series C+", "Bridge", "Growth", or null. Only fill if is_raising is true or clearly mentioned.
- seeking_amount: the target raise as a short string with currency, e.g. "$500K", "$2M", "₺10M", "€1.5M". Null if not stated. Only fill if is_raising is true.
- activity_type: one of "raising" (currently open), "recent_round" (just closed), "demo_day" (in accelerator cohort), or null. See special context blocks below.
- raising_evidence: a STATUS LABEL or SECTION HEADER from the page (e.g. "Ön Yatırım", "Pre Investment", "Fonlanıyor", "SEED FUNDING", "raised $2M seed"). MUST NOT be the company's own name, a URL, or a bare amount — it has to be a phrase stating raising activity. Null if no such phrase exists on the page.

CRITICAL RULES:
1. Extract EVERY startup/company on the page — do NOT skip any.
2. ALL text MUST be in English — translate Turkish/other languages (but keep founder names in their original form).
3. Description must explain what the company DOES.
4. Do NOT extract: the VC firm / platform itself, fund names, events, universities, accelerator program names, large corporations (Microsoft, Google, OpenAI, etc.), news article subjects.
5. Do NOT mark is_raising=true unless there is EXPLICIT textual evidence — default to false.
6. Return ONLY a valid JSON array, nothing else.
"""

EXTRACT_PROMPT_PART2 = """
Return as JSON array:
[{"name": "...", "description": "...", "industry": "...", "location": "...", "website": "...", "founded_year": null, "founders": [], "is_raising": false, "activity_type": null, "funding_stage": null, "seeking_amount": null, "raising_evidence": null}]

PAGE CONTENT:
"""


CROWDFUNDING_INSTRUCTION = """
SPECIAL CONTEXT — EQUITY CROWDFUNDING PLATFORM:
This page is from an equity/reward crowdfunding platform. EVERY company listed here is ACTIVELY SEEKING INVESTMENT by definition — that is the entire purpose of these platforms.
- Set is_raising=true for every company UNLESS the page explicitly marks the campaign as "BAŞARILI" (successful), "KAPANDI" (closed), "SONLANDI" (ended), "FUNDED", "CLOSED", or shows 100%+ completion with past-tense wording.
- For seeking_amount: extract the target raise amount. Look for "Hedef" (target), "Toplam Hedef", "Funding Goal", a sum followed by "TL" / "₺" / "$" / "€". Format as "₺500K", "₺2M", "$1M", etc.
- For funding_stage: infer from amount and context — under ₺1M → "Pre-seed", ₺1-5M → "Seed", ₺5-15M → "Series A", else "Growth". If unsure, use "Seed".
- For raising_evidence: quote the "Ön Yatırım" / "Pre Investment" / "Fonlanıyor" / "SEED FUNDING" status tag verbatim — NEVER the company name or a bare amount.
- Skip items that are clearly news articles, blog posts, or platform announcements — only extract actual company campaigns.
- Default activity_type="raising".
"""

NEWS_INSTRUCTION = """
SPECIAL CONTEXT — TURKISH STARTUP NEWS SITE:
This page is from a Turkish startup news site (e.g. Webrazzi). It mixes articles about BOTH Turkish and global startup rounds. We ONLY care about TURKISH startups.

CRITICAL FILTERING RULES:
- EXTRACT ONLY companies that the article explicitly identifies as TURKISH. Look for phrases like:
  - "Türk girişim", "Türkiye'nin", "İstanbul merkezli", "Ankara merkezli", "yerli girişim", "Türkiye kurumsal"
  - "Turkish startup", "Istanbul-based", "Turkey-based"
  - Founder/CEO explicitly described as Turkish
  - Explicitly mentions HQ in Turkey
- SKIP all companies from the US, UK, Germany, China, India, or any other country — even if the article is in Turkish. Webrazzi often translates foreign funding news; those entries MUST be skipped.
- If you cannot determine the company is Turkish with high confidence, SKIP IT.

For Turkish companies that pass the filter:
- Set is_raising=true.
- Set location="Istanbul, Turkey" (or actual city if mentioned) — NOT null.
- For seeking_amount: extract the round size from the article, e.g. "$2M", "₺10M".
- For funding_stage: the stage mentioned (pre-seed, seed, Series A, etc.).
- For raising_evidence: quote a verb phrase about raising from the article, e.g. "3 milyon dolar yatırım aldı", "raised a $2M seed round".
- Set activity_type="recent_round".
- Do NOT extract VCs, funds, or investors as companies.
"""

VC_PORTFOLIO_INSTRUCTION = """
SPECIAL CONTEXT — VC FIRM PORTFOLIO PAGE:
This page is the portfolio listing of a Turkey-focused VC firm. However, Turkey-focused VCs ALSO invest in non-Turkish (US/UK/EU) companies. We ONLY want the TURKISH ones.

STRICT TURKEY-ONLY FILTER:
- Extract a company ONLY if there is EXPLICIT textual evidence it is headquartered in Turkey. Signals:
  - Description says "Turkish", "Türk", "Istanbul-based", "based in Istanbul/Ankara/Izmir", "Turkey-based"
  - The company is explicitly founded in Turkey
  - HQ listed as a Turkish city
- SKIP the company if the description mentions:
  - "UK-based", "US-based", "headquartered in London/New York/San Francisco/Berlin/Amsterdam/Dublin/Tel Aviv"
  - The company is known to be incorporated outside Turkey even with Turkish founders
- If you CANNOT verify Turkey HQ from the page content, SKIP THE COMPANY. Do NOT default to Turkey.
- Set location only to the actual Turkish city stated — never guess.

For companies that pass the Turkey check:
- Set is_raising=true
- Set activity_type="vc_portfolio"
- For seeking_amount: leave null unless an exact round amount is visible on the page.
- For funding_stage: infer if mentioned (Seed, Series A, etc.), else leave null.
- For raising_evidence: use the phrase "Portfolio Company" or "Backed by <VC firm name>".
- Do NOT extract the VC firm itself, team/partner bios, LPs, or fund names.
"""

DEMO_DAY_INSTRUCTION = """
SPECIAL CONTEXT — ACCELERATOR / DEMO DAY PAGE:
This page lists startups from an accelerator cohort or demo day. These startups are presenting to investors and are implicitly looking for funding.
- Set is_raising=true for every actual startup (not the accelerator/program itself).
- For seeking_amount: leave null unless an explicit target is stated.
- For funding_stage: typically "Pre-seed" or "Seed" unless the accelerator is later-stage.
- For raising_evidence: use the phrase "Demo Day Cohort" or quote any "currently raising" language on the page.
- Default activity_type="demo_day".
- Do NOT extract the accelerator/VC itself, team/mentor bios, or sponsor brands.
"""


def build_extract_prompt(country: str | None = None, source_mode: str = "default") -> str:
    country_instruction = ""
    if country and source_mode in ("crowdfunding", "demo_day"):
        # These sources are country-specific by construction — safe to default location.
        country_instruction = (
            f"\n- This is a {country}-focused platform. "
            f"Companies listed here are based in {country}. "
            f"Set location to \"{country}\" for companies where location is not explicitly mentioned.\n"
        )
    elif source_mode == "news":
        # News sites mix local + global — the LLM must NOT default location.
        country_instruction = (
            "\n- This is a news site that covers BOTH local and global startup rounds. "
            "Set 'location' to the company's ACTUAL headquarters as mentioned in the article "
            "(e.g. 'Istanbul, Turkey', 'San Francisco, USA', 'London, UK'). "
            "If the article does not state the company's HQ or country, set location to null — "
            "NEVER default to the site's country.\n"
        )
    extra = ""
    if source_mode == "crowdfunding":
        extra = CROWDFUNDING_INSTRUCTION
    elif source_mode == "news":
        extra = NEWS_INSTRUCTION
    elif source_mode == "vc_portfolio":
        extra = VC_PORTFOLIO_INSTRUCTION
    elif source_mode == "demo_day":
        extra = DEMO_DAY_INSTRUCTION
    return EXTRACT_PROMPT_PART1 + country_instruction + extra + EXTRACT_PROMPT_PART2


@dataclass
class ScrapedCompany:
    name: str
    description: str = ""
    website: str = ""
    industry: str = ""
    location: str = ""
    source_url: str = ""
    source_name: str = ""
    page_url: str = ""
    founded_year: int | None = None
    founders: list[str] | None = None
    is_raising: bool = False
    activity_type: str | None = None  # raising | recent_round | demo_day
    funding_stage: str | None = None
    seeking_amount: str | None = None
    raising_evidence: str | None = None


def is_valid_company(name: str, description: str) -> bool:
    """Filter out non-company entries."""
    name_lower = name.lower().strip()

    # Too short or too long
    if len(name_lower) < 2 or len(name_lower) > 120:
        return False

    # Blacklisted names
    if name_lower in BLACKLIST_NAMES:
        return False

    # Looks like a generic category, not a company name
    generic_patterns = [
        r'^(fintech|saas|ai|iot|gaming|e-?commerce|health\s*tech|ed\s*tech|bio\s*tech|deep\s*tech)$',
        r'^(technology|software|hardware|digital|mobile|cloud|data|cyber)$',
        r'^(startup|venture|fund|capital|holding|group|angel|investment)s?$',
        r'teknoloji(leri)?$',  # Turkish for "technologies"
        r'sigorta teknolojileri',
        r'sağlık teknolojileri',
        r'eğitim teknolojileri',
        r'finansal teknolojiler',
        r'nesnelerin interneti',
    ]
    for pat in generic_patterns:
        if re.match(pat, name_lower, re.IGNORECASE):
            return False

    # Description indicates it's not a real company
    desc_lower = (description or "").lower()
    if any(phrase in desc_lower for phrase in [
        "where", "spent time", "worked at", "previously at",
        "description missing", "description not available", "no description",
        "high-profile top tech", "not a company",
    ]):
        return False

    return True


async def fetch_page_playwright(url: str) -> str | None:
    """Fetch a page using headless Chromium for JS-rendered sites."""
    if not _playwright_available:
        return None
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            # domcontentloaded is much more reliable than networkidle on tracker-heavy sites
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            # Give client-side hydration a moment to run
            try:
                await page.wait_for_load_state("load", timeout=8000)
            except Exception:
                pass
            html = await page.content()
            await browser.close()
            return html
    except Exception as e:
        print(f"  Playwright error for {url}: {e}")
    return None


async def fetch_page(client: httpx.AsyncClient, url: str, use_browser: bool = False) -> str | None:
    if use_browser:
        return await fetch_page_playwright(url)
    try:
        resp = await client.get(url, headers=HEADERS, follow_redirects=True, timeout=20.0)
        if resp.status_code == 200 and "text/html" in resp.headers.get("content-type", ""):
            return resp.text
    except Exception as e:
        print(f"  Fetch error for {url}: {e}")
    return None


def get_base_domain(url: str) -> str:
    return urlparse(url).netloc.lower().replace("www.", "")


def is_same_site(url: str, base_domain: str) -> bool:
    return get_base_domain(url) == base_domain


def should_skip(url: str) -> bool:
    url_lower = url.lower()
    return any(kw in url_lower for kw in SKIP_KEYWORDS)


def html_to_text(html: str, max_chars: int = 60000) -> str:
    """Convert HTML to text preserving links so Gemini can see URLs."""
    soup = BeautifulSoup(html, "lxml")

    # Remove noise
    for tag in soup.select("script, style, noscript, svg, iframe, nav, footer, header"):
        tag.decompose()

    # Convert links to text with URL preserved
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        text = a.get_text(strip=True)
        if href and text and not href.startswith(("#", "javascript:", "mailto:")):
            a.replace_with(f"{text} ({href})")

    text = soup.get_text(separator="\n", strip=True)
    text = re.sub(r'\n{3,}', '\n\n', text)

    if len(text) > max_chars:
        text = text[:max_chars] + "\n...[truncated]"

    return text


def collect_internal_links(html: str, base_url: str, base_domain: str) -> tuple[list[str], list[str]]:
    """Collect all internal links, separated into priority and others."""
    soup = BeautifulSoup(html, "lxml")
    priority = []
    others = []
    seen = set()

    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if not href or href.startswith(("#", "javascript:", "mailto:", "tel:")):
            continue
        full_url = urljoin(base_url, href).split("#")[0].rstrip("/")
        if full_url in seen or not is_same_site(full_url, base_domain):
            continue
        if should_skip(full_url):
            continue
        seen.add(full_url)

        url_lower = full_url.lower()
        if any(kw in url_lower for kw in PRIORITY_KEYWORDS):
            priority.append(full_url)
        else:
            others.append(full_url)

    return priority, others


def find_pagination_links(html: str, base_url: str, base_domain: str) -> list[str]:
    """Find pagination links (page/2, ?page=2, etc.)."""
    soup = BeautifulSoup(html, "lxml")
    pages = []
    seen = set()

    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        full_url = urljoin(base_url, href).split("#")[0].rstrip("/")
        if full_url in seen or not is_same_site(full_url, base_domain):
            continue
        seen.add(full_url)

        url_lower = full_url.lower()
        if any(re.search(pat, url_lower) for pat in PAGINATION_PATTERNS):
            pages.append(full_url)

        link_text = a.get_text(strip=True).lower()
        if link_text in ("next", "next page", "load more", "show more", "view more", ">", "»", "sonraki"):
            pages.append(full_url)

    return pages


async def extract_with_gemini(client: httpx.AsyncClient, page_text: str, country: str | None = None, source_mode: str = "default") -> list[dict]:
    """Send page text to Gemini Flash and get structured company data."""
    if not GOOGLE_API_KEY:
        print("WARNING: No GOOGLE_API_KEY set")
        return []

    prompt = build_extract_prompt(country, source_mode=source_mode)

    max_chunk = 50000
    chunks = []
    if len(page_text) > max_chunk:
        for i in range(0, len(page_text), max_chunk):
            chunk = page_text[i:i + max_chunk]
            chunks.append(chunk)
    else:
        chunks = [page_text]

    all_companies = []
    for chunk in chunks:
        payload = {
            "contents": [{"parts": [{"text": prompt + chunk}]}],
            "generationConfig": {
                "temperature": 0.1,
                "maxOutputTokens": 8192,
            }
        }

        for attempt in range(3):
            try:
                resp = await client.post(
                    f"{GEMINI_URL}?key={GOOGLE_API_KEY}",
                    json=payload,
                    timeout=60.0,
                )
                if resp.status_code == 429:
                    wait = 10 * (attempt + 1)
                    print(f"  Gemini rate limit, waiting {wait}s...")
                    await asyncio.sleep(wait)
                    continue

                if resp.status_code != 200:
                    print(f"  Gemini API error: {resp.status_code}")
                    break

                data = resp.json()
                text = data["candidates"][0]["content"]["parts"][0]["text"]

                text = text.strip()
                if text.startswith("```"):
                    text = re.sub(r'^```(?:json)?\s*', '', text)
                    text = re.sub(r'\s*```$', '', text)

                companies = json.loads(text)
                if isinstance(companies, list):
                    all_companies.extend(companies)
                break

            except Exception as e:
                print(f"  Gemini extraction error: {e}")
                if attempt < 2:
                    await asyncio.sleep(3)
                continue

        if len(chunks) > 1:
            await asyncio.sleep(1)

    return all_companies


async def extract_companies_from_page(
    client: httpx.AsyncClient,
    html: str,
    page_url: str,
    source_name: str,
    country: str | None = None,
    source_mode: str = "default",
) -> list[ScrapedCompany]:
    """Extract companies from a page using Gemini."""
    page_text = html_to_text(html)

    if len(page_text.strip()) < 100:
        return []

    raw = await extract_with_gemini(client, page_text, country=country, source_mode=source_mode)

    companies = []
    for item in raw:
        name = (item.get("name") or "").strip()
        description = (item.get("description") or "").strip()[:500]

        if not is_valid_company(name, description):
            continue

        raw_year = item.get("founded_year")
        founded_year = None
        if raw_year:
            try:
                yr = int(raw_year)
                if 1900 <= yr <= 2030:
                    founded_year = yr
            except (ValueError, TypeError):
                pass

        activity_type = (item.get("activity_type") or None)
        if isinstance(activity_type, str):
            activity_type = activity_type.strip().lower() or None
            if activity_type not in ("raising", "recent_round", "vc_portfolio", "demo_day"):
                activity_type = None

        raw_founders = item.get("founders") or []
        founders: list[str] = []
        if isinstance(raw_founders, list):
            for fn in raw_founders:
                if isinstance(fn, str) and 2 < len(fn.strip()) < 100:
                    founders.append(fn.strip())
        elif isinstance(raw_founders, str) and raw_founders.strip():
            founders = [p.strip() for p in re.split(r',|&| and ', raw_founders) if p.strip()]

        is_raising = bool(item.get("is_raising"))
        funding_stage = (item.get("funding_stage") or None)
        if isinstance(funding_stage, str):
            funding_stage = funding_stage.strip() or None
        seeking_amount = (item.get("seeking_amount") or None)
        if isinstance(seeking_amount, str):
            seeking_amount = seeking_amount.strip() or None
        raising_evidence = (item.get("raising_evidence") or None)
        if isinstance(raising_evidence, str):
            raising_evidence = raising_evidence.strip()[:200] or None

        # Validate is_raising per source mode.
        if is_raising:
            ev_lower = (raising_evidence or "").lower()
            name_lower = name.lower()
            ev_stripped = ev_lower.replace(name_lower, "").strip(" .,:;-()[]\"'")
            import re as _rre
            valid = False

            if activity_type == "demo_day":
                # demo_day: accept as long as evidence exists and isn't a past/closed term
                valid = bool(ev_stripped) and len(ev_stripped) >= 3
            elif source_mode == "vc_portfolio":
                # vc_portfolio: accept any company with evidence AND description doesn't flag non-Turkish origin
                valid = bool(ev_stripped) and len(ev_stripped) >= 3
                if valid:
                    activity_type = "vc_portfolio"
                    desc_lower = (description or "").lower()
                    NON_TR_MARKERS = [
                        "uk-based", "u.k.-based", "us-based", "u.s.-based",
                        "headquartered in london", "headquartered in new york",
                        "headquartered in san francisco", "headquartered in berlin",
                        "headquartered in amsterdam", "headquartered in dublin",
                        "headquartered in tel aviv", "based in london", "based in new york",
                        "based in the uk", "based in the us", "based in the united states",
                        "based in the united kingdom", "estonian company", "dutch company",
                        "german company", "french company",
                    ]
                    if any(m in desc_lower for m in NON_TR_MARKERS):
                        valid = False
            elif activity_type == "recent_round":
                # news article: evidence must describe a raise verb (raised / aldı / oldu / secured)
                NEWS_TRIGGERS = [
                    r"\braised?\b", r"\bsecured\b", r"\bsecures\b", r"\bclosed?\b (a|an|its)?\s*(pre[\s-]?seed|seed|series|round|funding)",
                    r"\byat[ıi]r[ıi]m ald[ıi]\b", r"\byat[ıi]r[ıi]m al[dm][ıi][şs]\b",
                    r"\btur(unu)? kapatt[ıi]\b", r"\btamamlad[ıi]\b",
                    r"\b(milyon|million)\s*(dolar|tl|lira|euro|avro|usd)\b",
                    r"\b\$\d", r"\b₺\d", r"\b€\d",
                ]
                valid = any(_rre.search(p, ev_lower) for p in NEWS_TRIGGERS)
            else:
                # crowdfunding / default: require positive raising trigger
                CLOSED_TOKENS = [
                    r"\bfonland[ıi]\b", r"\bkapand[ıi]\b",
                    r"\bba[şs]ar[ıi]l[ıi]\b", r"\bba[şs]aran(lar)?\b",
                    r"\bclosed\b", r"\bcompleted\b", r"\bsuccessful club\b",
                    r"\bfunded\b", r"\bended\b", r"\bpast\b",
                    r"\bfonlanmad[ıi]\b", r"\bfailed\b", r"\bunsuccessful\b",
                    r"\byak[ıi]nda\b", r"\bcoming soon\b", r"\bupcoming\b",
                ]
                RAISE_TRIGGERS = [
                    r"\b[öo]n yat[ıi]r[ıi]m\b",
                    r"\bpre[\s-]?investment\b",
                    r"\bfonlan[ıi]yor\b", r"\bfon topluyor\b",
                    r"\braising\b", r"\bopen round\b", r"\bopen campaign\b", r"\bactive campaign\b",
                    r"\byat[ıi]r[ıi]m ar[ıi]yor\b", r"\byat[ıi]r[ıi]m turu a[çc][ıi]k\b",
                    r"\ba[çc][ıi]k tur\b", r"\bcanl[ıi]\b", r"\blive campaign\b",
                    r"\bseeking (investment|funding)\b", r"\blooking for investors\b",
                    r"\b(seed|series a|pre[\s-]?seed|growth) funding\b",
                    r"\bfunding now\b", r"\bnow raising\b",
                ]
                has_closed = any(_rre.search(p, ev_lower) for p in CLOSED_TOKENS)
                has_trigger = ev_stripped and any(_rre.search(p, ev_stripped) for p in RAISE_TRIGGERS)
                valid = bool(has_trigger and not has_closed)

            if not valid:
                is_raising = False
                activity_type = None
                funding_stage = None
                seeking_amount = None
                raising_evidence = None

        companies.append(ScrapedCompany(
            name=name,
            description=description,
            website=(item.get("website") or "").strip(),
            industry=(item.get("industry") or "").strip(),
            location=(item.get("location") or "").strip(),
            source_url=page_url,
            source_name=source_name,
            page_url=page_url,
            founded_year=founded_year,
            founders=founders or None,
            is_raising=is_raising,
            activity_type=activity_type,
            funding_stage=funding_stage,
            seeking_amount=seeking_amount,
            raising_evidence=raising_evidence,
        ))

    return companies


def _score(c: ScrapedCompany) -> int:
    return (
        len(c.description) + len(c.industry) + len(c.location) + len(c.website)
        + (10 if c.founded_year else 0)
        + (20 if c.founders else 0)
        + (30 if c.is_raising else 0)
        + (10 if c.seeking_amount else 0)
    )


def _merge(into: ScrapedCompany, other: ScrapedCompany) -> ScrapedCompany:
    """Merge missing fields from other into into (keeps 'into' identity)."""
    if not into.description and other.description:
        into.description = other.description
    if not into.website and other.website:
        into.website = other.website
    if not into.industry and other.industry:
        into.industry = other.industry
    if not into.location and other.location:
        into.location = other.location
    if not into.founded_year and other.founded_year:
        into.founded_year = other.founded_year
    if not into.founders and other.founders:
        into.founders = other.founders
    if other.is_raising and not into.is_raising:
        into.is_raising = True
        into.funding_stage = into.funding_stage or other.funding_stage
        into.seeking_amount = into.seeking_amount or other.seeking_amount
        into.raising_evidence = into.raising_evidence or other.raising_evidence
    return into


def deduplicate(companies: list[ScrapedCompany]) -> list[ScrapedCompany]:
    """Deduplicate companies, merging fields so raising signals + founders survive."""
    by_key: dict[str, ScrapedCompany] = {}
    for c in companies:
        key = re.sub(r'[^a-z0-9]', '', c.name.lower())
        if len(key) <= 1:
            continue
        existing = by_key.get(key)
        if existing is None:
            by_key[key] = c
        else:
            if _score(c) > _score(existing):
                by_key[key] = _merge(c, existing)
            else:
                by_key[key] = _merge(existing, c)
    return list(by_key.values())


async def crawl_and_extract(
    url: str,
    source_name: str,
    topics: list[str] | None = None,
    max_pages: int = 30,
    country: str | None = None,
    source_mode: str = "default",
    force_browser: bool = False,
) -> tuple[list[ScrapedCompany], int]:
    """Crawl a website thoroughly and use Gemini to extract companies."""
    base_domain = get_base_domain(url)
    url = url.rstrip("/")

    visited = set()
    all_companies = []
    pages_crawled = 0

    async with httpx.AsyncClient(timeout=30.0) as client:
        print(f"[{source_name}] Starting crawl: {url} (force_browser={force_browser})")
        html = await fetch_page(client, url, use_browser=force_browser)

        # If httpx returns too little content, try Playwright (JS-rendered site)
        use_browser = False
        if html:
            text_len = len(html_to_text(html, max_chars=5000))
            if text_len < 500 and _playwright_available:
                print(f"  [{source_name}] Page has little content ({text_len} chars), trying headless browser...")
                browser_html = await fetch_page_playwright(url)
                if browser_html and len(html_to_text(browser_html, max_chars=5000)) > text_len:
                    html = browser_html
                    use_browser = True
                    print(f"  [{source_name}] Browser fetched more content")
        elif _playwright_available:
            print(f"  [{source_name}] httpx failed, trying headless browser...")
            html = await fetch_page_playwright(url)
            if html:
                use_browser = True

        if not html:
            print(f"[{source_name}] Failed to fetch starting page")
            return [], 0

        visited.add(url)
        pages_crawled += 1

        homepage_companies = await extract_companies_from_page(client, html, url, source_name, country=country, source_mode=source_mode)
        print(f"  [{source_name}] {url} -> {len(homepage_companies)} companies")

        priority_links, other_links = collect_internal_links(html, url, base_domain)
        print(f"  [{source_name}] Found {len(priority_links)} priority links, {len(other_links)} other links")

        priority_companies = []
        pagination_links = []
        detail_page_links = []

        listing_links = []
        for link in priority_links:
            if link in visited:
                continue
            path = urlparse(link).path.rstrip("/")
            segments = [s for s in path.split("/") if s]
            if len(segments) <= 2:
                listing_links.append(link)
            else:
                detail_page_links.append(link)

        # Step 2: Crawl listing pages
        for link in listing_links:
            if link in visited or pages_crawled >= max_pages:
                continue
            page_html = await fetch_page(client, link, use_browser=force_browser)
            if not page_html:
                continue
            visited.add(link)
            pages_crawled += 1

            found = await extract_companies_from_page(client, page_html, link, source_name, country=country, source_mode=source_mode)
            priority_companies.extend(found)
            print(f"  [{source_name}] {link} -> {len(found)} companies")

            page_pagination = find_pagination_links(page_html, link, base_domain)
            for pg in page_pagination:
                if pg not in visited:
                    pagination_links.append(pg)

            sub_priority, _ = collect_internal_links(page_html, link, base_domain)
            for sl in sub_priority:
                if sl not in visited:
                    sl_path = urlparse(sl).path.rstrip("/")
                    sl_segments = [s for s in sl_path.split("/") if s]
                    if len(sl_segments) <= 2:
                        listing_links.append(sl)
                    else:
                        detail_page_links.append(sl)

            await asyncio.sleep(0.3)

        # Step 3: Follow pagination
        for pg_link in pagination_links:
            if pg_link in visited or pages_crawled >= max_pages:
                continue
            pg_html = await fetch_page(client, pg_link, use_browser=force_browser)
            if not pg_html:
                continue
            visited.add(pg_link)
            pages_crawled += 1

            found = await extract_companies_from_page(client, pg_html, pg_link, source_name, country=country, source_mode=source_mode)
            priority_companies.extend(found)
            print(f"  [{source_name}] {pg_link} -> {len(found)} companies (page)")

            more_pages = find_pagination_links(pg_html, pg_link, base_domain)
            for mp in more_pages:
                if mp not in visited:
                    pagination_links.append(mp)

            await asyncio.sleep(0.3)

        all_companies.extend(homepage_companies)
        all_companies.extend(priority_companies)

        unique_so_far = len(deduplicate(all_companies))

        # Step 4: Enrich from detail pages if needed
        companies_without_desc = sum(1 for c in all_companies if not c.description)
        if unique_so_far > 0 and companies_without_desc > unique_so_far * 0.5:
            detail_limit = min(len(detail_page_links), 30)
            print(f"  [{source_name}] Enriching: crawling up to {detail_limit} detail pages...")
            for link in detail_page_links[:detail_limit]:
                if link in visited or pages_crawled >= max_pages:
                    continue
                page_html = await fetch_page(client, link, use_browser=force_browser)
                if not page_html:
                    continue
                visited.add(link)
                pages_crawled += 1

                found = await extract_companies_from_page(client, page_html, link, source_name, country=country, source_mode=source_mode)
                all_companies.extend(found)
                print(f"  [{source_name}] {link} -> {len(found)} companies (detail)")
                await asyncio.sleep(0.3)

        # Step 5: If few results (or crowdfunding, where detail pages hold target amounts), try detail + other pages
        unique_so_far = len(deduplicate(all_companies))
        if unique_so_far < 5 or source_mode == "crowdfunding":
            print(f"  [{source_name}] Few results ({unique_so_far}), trying more pages...")
            for link in detail_page_links[:25]:
                if link in visited or pages_crawled >= max_pages:
                    continue
                page_html = await fetch_page(client, link, use_browser=force_browser)
                if not page_html:
                    continue
                visited.add(link)
                pages_crawled += 1
                found = await extract_companies_from_page(client, page_html, link, source_name, country=country, source_mode=source_mode)
                all_companies.extend(found)
                print(f"  [{source_name}] {link} -> {len(found)} companies")
                await asyncio.sleep(0.3)

            for link in other_links[:15]:
                if link in visited or pages_crawled >= max_pages:
                    continue
                page_html = await fetch_page(client, link, use_browser=force_browser)
                if not page_html:
                    continue
                visited.add(link)
                pages_crawled += 1
                found = await extract_companies_from_page(client, page_html, link, source_name, country=country, source_mode=source_mode)
                all_companies.extend(found)
                print(f"  [{source_name}] {link} -> {len(found)} companies")
                await asyncio.sleep(0.3)

    all_companies = deduplicate(all_companies)
    print(f"[{source_name}] Done: {len(all_companies)} unique companies from {pages_crawled} pages")
    return all_companies, pages_crawled
