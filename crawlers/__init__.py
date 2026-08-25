from crawlers.alio import AlioCrawler
from crawlers.cleaneye import CleanEyeCrawler
from crawlers.gojobs import GoJobsCrawler
from crawlers.localgov import LocalGovCrawler

CRAWLERS = [AlioCrawler, CleanEyeCrawler, GoJobsCrawler, LocalGovCrawler]

__all__ = ["AlioCrawler", "CleanEyeCrawler", "GoJobsCrawler", "LocalGovCrawler", "CRAWLERS"]
