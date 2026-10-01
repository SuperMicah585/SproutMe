class EventScraper:
    """Daily scrape lives in a separate PythonAnywhere task, not this app."""

    def scrape(self):
        return {"success": False, "message": "Scraping is handled by a scheduled task, not this process."}
