"""
Playwright 브라우저 클라이언트 (재사용 가능)

사용법:
    from src.utils.browser import BrowserClient

    with BrowserClient() as client:
        html = client.get_page_html("https://example.com")
        client.screenshot("https://example.com", "output.png")
"""

from contextlib import contextmanager

from playwright.sync_api import Browser, BrowserContext, Page, sync_playwright


class BrowserClient:
    """Playwright 기반 헤드리스 브라우저 클라이언트."""

    def __init__(self, headless: bool = True, timeout: int = 30_000):
        self._headless = headless
        self._timeout = timeout
        self._pw = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None

    def __enter__(self) -> "BrowserClient":
        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.launch(headless=self._headless)
        self._context = self._browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/131.0.0.0 Safari/537.36",
        )
        self._context.set_default_timeout(self._timeout)
        return self

    def __exit__(self, *args) -> None:
        if self._context:
            self._context.close()
        if self._browser:
            self._browser.close()
        if self._pw:
            self._pw.stop()

    def new_page(self) -> Page:
        """새 페이지 탭을 생성한다."""
        if not self._context:
            raise RuntimeError("BrowserClient must be used as context manager")
        return self._context.new_page()

    def get_page_html(self, url: str, wait_until: str = "domcontentloaded") -> str:
        """URL의 렌더링된 HTML을 반환한다."""
        page = self.new_page()
        try:
            page.goto(url, wait_until=wait_until)
            return page.content()
        finally:
            page.close()

    def get_page_text(self, url: str, wait_until: str = "domcontentloaded") -> str:
        """URL의 텍스트 콘텐츠를 반환한다."""
        page = self.new_page()
        try:
            page.goto(url, wait_until=wait_until)
            return page.inner_text("body")
        finally:
            page.close()

    def screenshot(self, url: str, path: str, full_page: bool = True) -> None:
        """URL의 스크린샷을 저장한다."""
        page = self.new_page()
        try:
            page.goto(url, wait_until="networkidle")
            page.screenshot(path=path, full_page=full_page)
        finally:
            page.close()


@contextmanager
def browser_client(headless: bool = True, timeout: int = 30_000):
    """BrowserClient를 컨텍스트 매니저 함수로 제공한다."""
    client = BrowserClient(headless=headless, timeout=timeout)
    with client:
        yield client
