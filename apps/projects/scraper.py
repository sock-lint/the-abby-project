import hashlib
import requests
from bs4 import BeautifulSoup
from django.core.cache import cache

def scrape_instructables(url):
    """
    Fetch an Instructables URL and extract metadata.
    Returns dict with: title, author, thumbnail_url, step_count, category.
    Caches results in Redis for 24 hours.
    """
    # Cache key from URL hash
    cache_key = f"instructables:{hashlib.md5(url.encode()).hexdigest()}"
    cached = cache.get(cache_key)
    if cached:
        return cached

    # Validate URL
    if not url or 'instructables.com' not in url:
        raise ValueError("Invalid Instructables URL")

    # Fetch page
    try:
        resp = requests.get(url, timeout=10, headers={
            'User-Agent': 'Mozilla/5.0 (compatible; SummerForge/1.0)'
        })
        resp.raise_for_status()
    except requests.RequestException as e:
        raise ValueError(f"Failed to fetch URL: {e}")

    soup = BeautifulSoup(resp.text, 'html.parser')

    # Extract metadata
    title = ''
    title_tag = soup.find('h1')
    if title_tag:
        title = title_tag.get_text(strip=True)

    author = ''
    # Try meta author or the byline
    author_tag = soup.find('a', class_='header-author') or soup.find('meta', attrs={'name': 'author'})
    if author_tag:
        author = author_tag.get('content', '') if author_tag.name == 'meta' else author_tag.get_text(strip=True)

    thumbnail_url = ''
    og_image = soup.find('meta', property='og:image')
    if og_image:
        thumbnail_url = og_image.get('content', '')

    # Count steps (Instructables uses step sections)
    steps = soup.find_all('section', class_=lambda c: c and 'step' in c.lower()) if soup else []
    if not steps:
        # Fallback: count h2 elements that look like steps
        steps = [h for h in soup.find_all('h2') if h.get_text(strip=True).lower().startswith('step')]
    step_count = len(steps)

    category = ''
    # Try breadcrumb or og:section
    og_section = soup.find('meta', property='article:section')
    if og_section:
        category = og_section.get('content', '')

    result = {
        'title': title,
        'author': author,
        'thumbnail_url': thumbnail_url,
        'step_count': step_count,
        'category': category,
        'url': url,
    }

    # Cache for 24 hours
    cache.set(cache_key, result, timeout=86400)
    return result
