"""
Download Microsoft Learn courses, learning paths, modules, and collections
as combined HTML and PDF files (one file per module).
Uses the Microsoft Learn Catalog API and the Collections (lists) API.
"""

import os
import re
import requests
import asyncio
from dataclasses import dataclass
from typing import Optional
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from playwright.async_api import async_playwright


# =============================================================================
# Constants
# =============================================================================

DEFAULT_COURSE_URL = "https://learn.microsoft.com/en-us/training/courses/ai-103t00"
DEFAULT_LEARNING_PATH_URL = "https://learn.microsoft.com/en-us/training/paths/develop-generative-ai-apps"
DEFAULT_MODULE_URL = "https://learn.microsoft.com/en-us/training/modules/prepare-azure-ai-development"
DEFAULT_COLLECTION_URL = "https://learn.microsoft.com/en-us/collections/p3zwhztxryzkqz"
CATALOG_API_URL = "https://learn.microsoft.com/api/catalog/"
COLLECTION_API_URL = "https://learn.microsoft.com/api/lists/"
# Folder name for collection items that are not inside any section
UNSECTIONED_ITEMS_NAME = "Other items"
OUTPUT_BASE_DIR = "output"
REQUEST_TIMEOUT = 30
CATALOG_TIMEOUT = 60

DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.0"
}

PAGE_TITLE_IGNORE = ("Knowledge check", "Module assessment", "Exercise - ")

HTML_STYLES = """
    body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; max-width: 900px; margin: 0 auto; padding: 20px; line-height: 1.6; }
    h1 { color: #0078d4; border-bottom: 2px solid #0078d4; padding-bottom: 10px; }
    h2 { color: #333; border-bottom: 1px solid #ddd; padding-bottom: 8px; margin-top: 0px; margin-bottom: 0px; }
    .section { margin-bottom: 40px; }
    .section-header { background: #f5f5f5; padding: 15px; border-radius: 5px; margin-bottom: 20px; }
    .section-header a { color: #0078d4; text-decoration: none; }
    .section-header a:hover { text-decoration: underline; }
    img { max-width: 100%; height: auto; }
    pre { background: #f4f4f4; padding: 15px; overflow-x: auto; border-radius: 5px; }
    code { background: #f4f4f4; padding: 2px 5px; border-radius: 3px; }
    table { border-collapse: collapse; width: 100%; margin: 15px 0; }
    th, td { border: 1px solid #ddd; padding: 8px; text-align: left; }
    th { background: #f5f5f5; }
    .NOTE, .TIP, .IMPORTANT { padding: 12px 15px; margin: 15px 0; border-radius: 5px; border-left: 4px solid; }
    .IMPORTANT { background-color: #e7f3ff; border-color: #0078d4; }
    .IMPORTANT > p:first-child { font-weight: bold; color: #0078d4; margin-top: 0; }
    .TIP { background-color: #e8f5e9; border-color: #4caf50; }
    .TIP > p:first-child { font-weight: bold; color: #2e7d32; margin-top: 0; }
    .NOTE { background-color: #f3e5f5; border-color: #9c27b0; }
    .NOTE > p:first-child { font-weight: bold; color: #7b1fa2; margin-top: 0; }
"""


# =============================================================================
# URL Helpers
# =============================================================================


def is_course_url(url: str) -> bool:
    """Check if a URL is a Microsoft Learn course URL."""
    return "/courses/" in url


def is_learning_path_url(url: str) -> bool:
    """Check if a URL is a Microsoft Learn learning path URL."""
    return "/paths/" in url


def is_module_url(url: str) -> bool:
    """Check if a URL is a Microsoft Learn module URL."""
    return "/modules/" in url


def is_collection_url(url: str) -> bool:
    """Check if a URL is a Microsoft Learn collection URL."""
    return "/collections/" in url


def clean_url(url: str) -> str:
    """Remove query parameters from a URL."""
    parsed = urlparse(url)
    return f"{parsed.scheme}://{parsed.netloc}{parsed.path}"


# =============================================================================
# Data Classes
# =============================================================================


@dataclass
class PageContent:
    """Represents extracted content from a web page."""

    title: str
    content: str
    url: str


@dataclass
class CollectionItem:
    """A single entry (learning path, module, course, ...) in a collection."""

    title: str
    url: str


@dataclass
class CollectionSection:
    """A named group of items inside a collection."""

    name: str
    items: list[CollectionItem]


@dataclass
class Collection:
    """A Microsoft Learn collection and its sections."""

    name: str
    sections: list[CollectionSection]
    # Items that are not inside any section
    unsectioned_items: list[CollectionItem]


# =============================================================================
# HTTP Client
# =============================================================================


class HttpClient:
    """HTTP client for making requests with consistent configuration."""

    def __init__(self, headers: Optional[dict] = None, timeout: int = REQUEST_TIMEOUT):
        self.headers = headers or DEFAULT_HEADERS
        self.timeout = timeout

    def get(self, url: str, **kwargs) -> requests.Response:
        """Make a GET request with default headers and timeout."""
        request_headers = kwargs.pop("headers", self.headers)
        request_timeout = kwargs.pop("timeout", self.timeout)
        return requests.get(
            url, headers=request_headers, timeout=request_timeout, **kwargs
        )


# =============================================================================
# Catalog Service
# =============================================================================


class CatalogService:
    """Service for interacting with the Microsoft Learn Catalog API."""

    def __init__(self, http_client: Optional[HttpClient] = None):
        self.http_client = http_client or HttpClient(timeout=CATALOG_TIMEOUT)
        self._catalog: Optional[dict] = None

    def fetch(self) -> Optional[dict]:
        """Fetch the Microsoft Learn Catalog API."""
        try:
            response = self.http_client.get(CATALOG_API_URL)
            response.raise_for_status()
            self._catalog = response.json()
            return self._catalog
        except requests.RequestException as e:
            print(f"Error fetching catalog: {e}")
            return None

    @property
    def catalog(self) -> Optional[dict]:
        """Get the cached catalog, fetching if necessary."""
        if self._catalog is None:
            self._catalog = self.fetch()
        return self._catalog

    def get_course_learning_paths(self, course_url: str) -> list[str]:
        """Extract all learning path URLs for a given course."""
        catalog = self.catalog
        if not catalog:
            return []

        course_id = self._extract_id_from_url(course_url)
        target_course = self._find_course_by_id(course_id, catalog.get("courses", []))

        if not target_course:
            print(f"Course '{course_id}' not found in catalog.")
            return []

        study_guide = target_course.get("study_guide", [])
        learning_path_uids = [
            item["uid"] for item in study_guide if item.get("type") == "learningPath"
        ]

        lp_lookup = {
            lp.get("uid"): lp.get("url") for lp in catalog.get("learningPaths", [])
        }

        path_urls = []
        for uid in learning_path_uids:
            url = lp_lookup.get(uid)
            if url:
                path_urls.append(self._clean_url(url))

        return path_urls

    def get_learning_path_modules(self, path_url: str) -> list[str]:
        """Get all module URLs for a learning path."""
        catalog = self.catalog
        if not catalog:
            return []

        path_name = self._extract_id_from_url(path_url)
        target_lp = self._find_learning_path_by_name(
            path_name, catalog.get("learningPaths", [])
        )

        if not target_lp:
            return []

        module_uids = target_lp.get("modules", [])
        module_lookup = {
            mod.get("uid"): mod.get("url") for mod in catalog.get("modules", [])
        }

        module_urls = []
        for uid in module_uids:
            url = module_lookup.get(uid)
            if url:
                module_urls.append(self._clean_url(url))

        return module_urls

    @staticmethod
    def _extract_id_from_url(url: str) -> str:
        """Extract the ID from a URL."""
        return url.rstrip("/").split("/")[-1]

    @staticmethod
    def _clean_url(url: str) -> str:
        """Remove query parameters from URL."""
        return clean_url(url)

    @staticmethod
    def _find_course_by_id(course_id: str, courses: list[dict]) -> Optional[dict]:
        """Find a course by its ID (case-insensitive partial match)."""
        course_id_lower = course_id.lower()
        for course in courses:
            uid = course.get("uid", "")
            if course_id_lower in uid.lower():
                return course
        return None

    @staticmethod
    def _find_learning_path_by_name(
        path_name: str, learning_paths: list[dict]
    ) -> Optional[dict]:
        """Find a learning path whose URL ends with the given name."""
        for lp in learning_paths:
            lp_url = clean_url(lp.get("url", ""))
            if CatalogService._extract_id_from_url(lp_url) == path_name:
                return lp
        return None


# =============================================================================
# Collection Service
# =============================================================================


class CollectionService:
    """Service for reading Microsoft Learn collections."""

    def __init__(self, http_client: Optional[HttpClient] = None):
        self.http_client = http_client or HttpClient()

    def fetch(self, collection_url: str) -> Optional[Collection]:
        """Fetch a collection and its sections from the lists API."""
        collection_id = collection_url.rstrip("/").split("/")[-1]
        try:
            response = self.http_client.get(f"{COLLECTION_API_URL}{collection_id}")
            response.raise_for_status()
            data = response.json()
        except (requests.RequestException, ValueError) as e:
            print(f"Error fetching collection '{collection_id}': {e}")
            return None

        sections = [
            CollectionSection(
                name=section.get("name") or f"Section {i}",
                items=self._parse_items(section.get("items", [])),
            )
            for i, section in enumerate(data.get("sections") or [], 1)
        ]

        return Collection(
            name=data.get("name") or collection_id,
            sections=sections,
            unsectioned_items=self._parse_items(data.get("items") or []),
        )

    @staticmethod
    def _parse_items(raw_items: list[dict]) -> list[CollectionItem]:
        """Convert raw API items to CollectionItem objects."""
        items = []
        for raw in raw_items:
            data = raw.get("data") or {}
            url = data.get("rawUrl") or data.get("url")
            if not url:
                continue
            url = clean_url(urljoin("https://learn.microsoft.com/", url))
            items.append(CollectionItem(title=data.get("title") or url, url=url))
        return items


# =============================================================================
# Content Service
# =============================================================================


class ContentService:
    """Service for fetching and processing web page content."""

    def __init__(self, http_client: Optional[HttpClient] = None):
        self.http_client = http_client or HttpClient()

    def fetch_page(self, url: str) -> PageContent:
        """Fetch and extract main content from a web page."""
        try:
            response = self.http_client.get(url)
            response.raise_for_status()

            soup = BeautifulSoup(response.content, "html.parser")
            title = self._extract_title(soup)
            content = self._extract_content(soup, url)

            return PageContent(title=title, content=content, url=url)

        except requests.RequestException as e:
            print(f"Error fetching {url}: {e}")
            return PageContent(
                title="Error", content=f"<p>Error loading content: {e}</p>", url=url
            )

    def fetch_unit_links(self, module_url: str) -> list[str]:
        """Fetch all unit links from a module URL."""
        try:
            response = self.http_client.get(module_url)
            response.raise_for_status()

            soup = BeautifulSoup(response.content, "html.parser")
            matching_links = set()

            for link in soup.find_all("a", href=True):
                href = link["href"]
                full_url = urljoin(module_url, href)
                parsed = urlparse(full_url)
                clean_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"

                if clean_url.startswith(module_url) and clean_url != module_url:
                    matching_links.add(clean_url)

            return sorted(matching_links, key=self._extract_sort_key)

        except requests.RequestException as e:
            print(f"Error fetching units from {module_url}: {e}")
            return []

    @staticmethod
    def _extract_title(soup: BeautifulSoup) -> str:
        """Extract the page title from the h1 tag."""
        title_tag = soup.find("h1")
        return title_tag.get_text(strip=True) if title_tag else "Untitled"

    @staticmethod
    def _extract_content(soup: BeautifulSoup, base_url: str) -> str:
        """Extract and clean the main content from the page."""
        content_div = (
            soup.find("article")
            or soup.find("main")
            or soup.find("div", class_="content")
        )

        if not content_div:
            return f"<p>Could not extract content from {base_url}</p>"

        ContentService._clean_unwanted_elements(content_div)
        ContentService._fix_image_urls(content_div, base_url)

        return str(content_div)

    @staticmethod
    def _clean_unwanted_elements(content_div) -> None:
        """Remove navigation and UI elements from content."""
        # Remove navigation elements
        for nav in content_div.find_all(["nav", "aside", "footer"]):
            nav.decompose()

        # Remove specific elements by class
        selectors_to_remove = [
            ".font-size-sm.margin-top-md.display-none-print",
            ".button.button-clear.button-primary.button-sm.inner-focus",
        ]
        for selector in selectors_to_remove:
            for elem in content_div.select(selector):
                elem.decompose()

        # Remove elements with background-color-body class
        for elem in content_div.find_all(
            class_=lambda x: x and "background-color-body" in x
        ):
            elem.decompose()

        # Remove <div> elements with xp-tag class (position tags)
        for elem in content_div.find_all("div", class_="xp-tag"):
            elem.decompose()

        # Remove <ul> elements with metadata page-metadata class
        for elem in content_div.find_all("ul", class_="metadata page-metadata"):
            elem.decompose()

        # Remove <div> elements with embeddedvideo class
        for elem in content_div.find_all("div", class_="embeddedvideo"):
            elem.decompose()

        # Remove <div> elements with CAUTION class
        for elem in content_div.find_all("div", class_="CAUTION"):
            elem.decompose()

        # Remove video pivot elements
        for elem in content_div.find_all("div", class_="zone has-pivot", attrs={"data-pivot": "video"}):
            elem.decompose()

    @staticmethod
    def _fix_image_urls(content_div, base_url: str) -> None:
        """Convert relative image URLs to absolute."""
        for img in content_div.find_all("img"):
            src = img.get("src")
            if src:
                img["src"] = urljoin(base_url, src)

            srcset = img.get("srcset")
            if srcset:
                new_srcset = []
                for item in srcset.split(","):
                    parts = item.strip().split(" ")
                    if parts:
                        parts[0] = urljoin(base_url, parts[0])
                        new_srcset.append(" ".join(parts))
                img["srcset"] = ", ".join(new_srcset)

    @staticmethod
    def _extract_sort_key(url: str) -> int | float:
        """Extract numeric prefix from URL path for sorting."""
        match = re.search(r"/([^/]+)$", url)
        if match:
            segment = match.group(1)
            num_match = re.match(r"^(\d+)", segment)
            if num_match:
                return int(num_match.group(1))
        return float("inf")


# =============================================================================
# HTML Generator
# =============================================================================


class HtmlGenerator:
    """Generator for creating combined HTML documents."""

    def __init__(self, content_service: Optional[ContentService] = None):
        self.content_service = content_service or ContentService()

    def generate_module_html(
        self,
        module_url: str,
        unit_links: list[str],
        output_dir: str,
        numbered_prefix: str,
    ) -> str:
        """Generate a combined HTML file with all unit contents."""
        module_data = self.content_service.fetch_page(module_url)
        safe_title = self._sanitize_filename(module_data.title)

        html_filename = f"{numbered_prefix}-{safe_title}.html"
        output_file = os.path.join(output_dir, html_filename)

        html_content = self._build_html(module_data, unit_links)

        with open(output_file, "w", encoding="utf-8") as f:
            f.write(html_content)

        return output_file

    def _build_html(self, module_data: PageContent, unit_links: list[str]) -> str:
        """Build the complete HTML document."""
        sections = []
        index = 1
        for link in unit_links:
            page_data = self.content_service.fetch_page(link)
            if page_data.title.startswith(PAGE_TITLE_IGNORE):
                continue
            sections.append(self._build_section(index, page_data))
            index += 1

        return self._build_document(module_data.title, sections)

    def _build_section(self, index: int, page_data: PageContent) -> str:
        """Build a single section HTML."""
        return f"""
    <div class="section">
        <div class="section-header">
            <h2>{index}. {page_data.title}</h2>
            <a href="{page_data.url}">{page_data.url}</a>
        </div>
        <div class="content">{page_data.content}</div>
    </div>"""

    def _build_document(self, title: str, sections: list[str]) -> str:
        """Build the complete HTML document structure."""
        sections_html = "\n".join(sections)

        return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    <style>{HTML_STYLES}</style>
</head>
<body>
    <h1>{title}</h1>
{sections_html}
</body>
</html>"""

    @staticmethod
    def _sanitize_filename(name: str) -> str:
        """Sanitize a string to be a valid filename."""
        # Replace invalid characters with underscore
        name = re.sub(r'[<>:"/\\|?*]', "_", name)
        # Remove leading/trailing spaces and dots
        name = name.strip(" .")
        # Limit length
        return name[:100]


# =============================================================================
# PDF Generator
# =============================================================================


class PdfGenerator:
    """Generator for converting HTML to PDF."""

    @staticmethod
    async def convert_html_to_pdf(html_file: str, pdf_file: str) -> str:
        """Convert an HTML file to PDF using Playwright."""
        async with async_playwright() as p:
            browser = await p.chromium.launch()
            page = await browser.new_page()

            html_path = os.path.abspath(html_file)
            await page.goto(f"file:///{html_path}")
            await page.wait_for_load_state("networkidle")

            await page.pdf(
                path=pdf_file,
                format="A4",
                margin={
                    "top": "20px",
                    "right": "20px",
                    "bottom": "20px",
                    "left": "20px",
                },
                print_background=True,
            )

            await browser.close()

        return pdf_file

    def generate(self, html_file: str) -> Optional[str]:
        """Generate PDF from HTML file, handling errors gracefully."""
        pdf_file = html_file.replace(".html", ".pdf")
        try:
            asyncio.run(self.convert_html_to_pdf(html_file, pdf_file))
            return pdf_file
        except Exception as e:
            print(f"      Warning: Failed to generate PDF: {e}")
            return None


# =============================================================================
# Course Processor
# =============================================================================


class CourseProcessor:
    """Main processor for extracting and generating course content."""

    def __init__(
        self,
        catalog_service: Optional[CatalogService] = None,
        content_service: Optional[ContentService] = None,
        html_generator: Optional[HtmlGenerator] = None,
        pdf_generator: Optional[PdfGenerator] = None,
        collection_service: Optional[CollectionService] = None,
    ):
        self.catalog_service = catalog_service or CatalogService()
        self.collection_service = collection_service or CollectionService()
        self.content_service = content_service or ContentService()
        self.html_generator = html_generator or HtmlGenerator(self.content_service)
        self.pdf_generator = pdf_generator or PdfGenerator()

    def process_course(
        self, course_url: str, output_base: str = OUTPUT_BASE_DIR
    ) -> list[str]:
        """Process a course and generate all output files."""
        print(f"\nFetching learning paths from: {course_url}")
        print("=" * 80)

        # Fetch course title to use as directory name
        course_title = self._fetch_course_title(course_url)
        course_dir_name = self._sanitize_dir_name(course_title)
        course_output_dir = os.path.join(output_base, course_dir_name)

        catalog = self.catalog_service.fetch()
        if not catalog:
            print("Failed to fetch catalog.")
            return []

        paths = self.catalog_service.get_course_learning_paths(course_url)

        if not paths:
            print("\nNo learning paths found.")
            return []

        self._display_learning_paths(paths)

        os.makedirs(course_output_dir, exist_ok=True)
        print(f"\n  Course: {course_title}")
        print(f"  Output directory: {course_output_dir}/")

        for i, path in enumerate(paths, 1):
            self._process_learning_path(path, i, course_output_dir)

        print(f"\n{'=' * 80}")
        print(f"All done! Output is in '{course_output_dir}/'")

        return paths

    def process_learning_path(
        self, path_url: str, output_base: str = OUTPUT_BASE_DIR
    ) -> list[str]:
        """Process a learning path directly (without a course wrapper)."""
        print(f"\nFetching learning path: {path_url}")
        print("=" * 80)

        path_data = self.content_service.fetch_page(path_url)
        path_dir_name = self._sanitize_dir_name(path_data.title)
        path_output_dir = os.path.join(output_base, path_dir_name)

        catalog = self.catalog_service.fetch()
        if not catalog:
            print("Failed to fetch catalog.")
            return []

        os.makedirs(path_output_dir, exist_ok=True)
        print(f"\n  Learning Path: {path_data.title}")
        print(f"  Output directory: {path_output_dir}/")

        modules = self.catalog_service.get_learning_path_modules(path_url)

        if not modules:
            print(f"  No modules found for this learning path.")
            return []

        for j, module_url in enumerate(modules, 1):
            self._process_module(module_url, j, path_output_dir)

        print(f"\n{'=' * 80}")
        print(f"All done! Output is in '{path_output_dir}/'")

        return modules

    def process_module(
        self, module_url: str, output_base: str = OUTPUT_BASE_DIR
    ) -> None:
        """Process a module URL directly (without a course or learning path)."""
        print(f"\nFetching module: {module_url}")
        print("=" * 80)

        module_data = self.content_service.fetch_page(module_url)
        module_dir_name = self._sanitize_dir_name(module_data.title)
        module_output_dir = os.path.join(output_base, module_dir_name)

        os.makedirs(module_output_dir, exist_ok=True)
        print(f"\n  Module: {module_data.title}")
        print(f"  Output directory: {module_output_dir}/")

        self._process_module(module_url, 1, module_output_dir)

        print(f"\n{'=' * 80}")
        print(f"All done! Output is in '{module_output_dir}/'")

    def process_collection(
        self, collection_url: str, output_base: str = OUTPUT_BASE_DIR
    ) -> list[str]:
        """Process a collection, keeping each section in its own folder."""
        print(f"\nFetching collection: {collection_url}")
        print("=" * 80)

        collection = self.collection_service.fetch(collection_url)
        if not collection:
            return []

        # Unsectioned items go in their own folder only when the collection
        # also has sections; otherwise they sit directly in the collection folder.
        groups = list(collection.sections)
        if collection.unsectioned_items and groups:
            groups.insert(
                0, CollectionSection(UNSECTIONED_ITEMS_NAME, collection.unsectioned_items)
            )

        item_count = len(collection.unsectioned_items) + sum(
            len(s.items) for s in collection.sections
        )
        if item_count == 0:
            print("\nThis collection is empty.")
            return []

        if not self.catalog_service.catalog:
            print("Failed to fetch catalog.")
            return []

        collection_dir = os.path.join(
            output_base, self._sanitize_dir_name(collection.name)
        )
        os.makedirs(collection_dir, exist_ok=True)
        print(f"\n  Collection: {collection.name}")
        print(f"  Output directory: {collection_dir}/")

        processed = []
        if groups:
            for i, section in enumerate(groups, 1):
                section_dir = os.path.join(
                    collection_dir, f"{i:02d}-{self._sanitize_dir_name(section.name)}"
                )
                os.makedirs(section_dir, exist_ok=True)
                print(f"\n{'-' * 80}")
                print(f"Section {i}: {section.name} ({len(section.items)} item(s))")
                print(f"  Created: {section_dir}/")
                processed += self._process_collection_items(section.items, section_dir)
        else:
            processed = self._process_collection_items(
                collection.unsectioned_items, collection_dir
            )

        print(f"\n{'=' * 80}")
        print(f"All done! Output is in '{collection_dir}/'")

        return processed

    def _process_collection_items(
        self, items: list[CollectionItem], output_dir: str
    ) -> list[str]:
        """Download each supported item, numbered in collection order."""
        processed = []
        index = 0
        for item in items:
            kind = self._training_kind(item.url)
            if kind is None:
                print(f"\n  Skipping (not a course, learning path or module): {item.title}")
                print(f"    {item.url}")
                continue

            index += 1
            if kind == "paths":
                self._process_learning_path(item.url, index, output_dir)
            elif kind == "modules":
                self._process_module(item.url, index, output_dir)
            else:
                self._process_course_item(item, index, output_dir)
            processed.append(item.url)
        return processed

    def _process_course_item(
        self, item: CollectionItem, index: int, output_dir: str
    ) -> None:
        """Process a course found inside a collection."""
        course_dir = os.path.join(
            output_dir, f"{index:02d}-{self._sanitize_dir_name(item.title)}"
        )
        os.makedirs(course_dir, exist_ok=True)
        print(f"\nCourse: {item.title}")
        print(f"  Created: {course_dir}/")

        paths = self.catalog_service.get_course_learning_paths(item.url)
        if not paths:
            print("    (No learning paths found for this course)")
        for i, path_url in enumerate(paths, 1):
            self._process_learning_path(path_url, i, course_dir)

    @staticmethod
    def _training_kind(url: str) -> Optional[str]:
        """Return 'courses', 'paths' or 'modules' for a training URL, else None.

        Only the top page of a course, path or module matches, so single
        unit pages and other content (docs, videos, ...) are skipped.
        """
        match = re.search(r"/training/(courses|paths|modules)/[^/]+/?$", url)
        return match.group(1) if match else None

    def _fetch_course_title(self, course_url: str) -> str:
        """Fetch the course page and extract the h1 title."""
        try:
            page_content = self.content_service.fetch_page(course_url)
            return page_content.title
        except Exception as e:
            print(f"Warning: Could not fetch course title: {e}")
            # Fallback to extracting from URL
            return course_url.rstrip("/").split("/")[-1]

    def _display_learning_paths(self, paths: list[str]) -> None:
        """Display the found learning paths."""
        print(f"\nFound {len(paths)} learning path(s):\n")
        for i, path in enumerate(paths, 1):
            print(f"{i}. {path}")
        print("\n" + "=" * 80)
        print("Creating directories and generating content...")

    def _process_learning_path(
        self, path_url: str, index: int, output_base: str
    ) -> None:
        """Process a single learning path."""
        print(f"\nFetching learning path page: {path_url}")

        path_data = self.content_service.fetch_page(path_url)
        path_name = self._sanitize_dir_name(path_data.title)
        numbered_name = f"{index:02d}-{path_name}"
        path_dir = os.path.join(output_base, numbered_name)

        os.makedirs(path_dir, exist_ok=True)
        print(f"\nLearning Path: {path_data.title}")
        print(f"  Created: {path_dir}/")

        modules = self.catalog_service.get_learning_path_modules(path_url)

        if modules:
            for j, module_url in enumerate(modules, 1):
                self._process_module(module_url, j, path_dir)
        else:
            print(f"    (No modules found for this learning path)")

    def _process_module(self, module_url: str, index: int, path_dir: str) -> None:
        """Process a single module."""
        module_name = module_url.rstrip("/").split("/")[-1]
        print(f"\n    Module: {module_name}")

        print(f"      Fetching units...")
        unit_links = self.content_service.fetch_unit_links(module_url)

        if not unit_links:
            print(f"      No units found for this module")
            return

        print(f"      Found {len(unit_links)} unit(s)")

        numbered_prefix = f"{index:02d}"
        html_file = self.html_generator.generate_module_html(
            module_url, unit_links, path_dir, numbered_prefix
        )
        print(f"      Generated: {html_file}")

        pdf_file = self.pdf_generator.generate(html_file)
        if pdf_file:
            print(f"      Generated: {pdf_file}")

    @staticmethod
    def _sanitize_dir_name(name: str) -> str:
        """Sanitize a string to be a valid directory name."""
        # Replace invalid characters with underscore
        name = re.sub(r'[<>:"/\\|?*]', "_", name)
        # Remove leading/trailing spaces and dots
        name = name.strip(" .")
        # Limit length
        return name[:100]


# =============================================================================
# User Input
# =============================================================================


def get_url_from_user(
    default_course_url: str = DEFAULT_COURSE_URL,
    default_learning_path_url: str = DEFAULT_LEARNING_PATH_URL,
    default_module_url: str = DEFAULT_MODULE_URL,
    default_collection_url: str = DEFAULT_COLLECTION_URL,
) -> str:
    """Prompt user for a Microsoft Learn URL (course, path, module, or collection)."""
    print(
        f"Enter a Microsoft Learn course, learning path, module, or collection URL"
        f"\n Course URL example: {default_course_url}"
        f"\n Learning path URL example: {default_learning_path_url}"
        f"\n Module URL example: {default_module_url}"
        f"\n Collection URL example: {default_collection_url}"
        f"\n  (press Enter to use default course URL: {default_course_url}):"
    )
    url = input("> ").strip()
    url = clean_url(url) if url else default_course_url
    return url if url else default_course_url


# =============================================================================
# Main Entry Point
# =============================================================================


def main() -> list[str]:
    """Main entry point."""
    url = get_url_from_user()
    processor = CourseProcessor()

    if is_collection_url(url):
        return processor.process_collection(url)
    elif is_course_url(url):
        return processor.process_course(url)
    elif is_learning_path_url(url):
        return processor.process_learning_path(url)
    elif is_module_url(url):
        processor.process_module(url)
        return []
    else:
        print(
            "Unrecognized URL type. Please provide a Microsoft Learn course URL\n"
            "  (containing '/courses/'), learning path URL (containing '/paths/'),\n"
            "  module URL (containing '/modules/'), or collection URL\n"
            "  (containing '/collections/')."
        )
        return []


if __name__ == "__main__":
    main()
