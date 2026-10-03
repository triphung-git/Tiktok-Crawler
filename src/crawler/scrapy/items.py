"""Scrapy items for TikTok crawler."""

import scrapy


class HashtagItem(scrapy.Item):
    """Item đại diện cho 1 video thu được từ trang hashtag."""
    hashtag = scrapy.Field()
    video_url = scrapy.Field()
    author = scrapy.Field()
    scraped_at = scrapy.Field()
    source_type = scrapy.Field()


class UserItem(scrapy.Item):
    """Item đại diện cho 1 video thu được từ trang profile user."""
    username = scrapy.Field()
    video_url = scrapy.Field()
    author = scrapy.Field()
    scraped_at = scrapy.Field()
    source_type = scrapy.Field()


class TikTokVideoItem(scrapy.Item):
    """Item tổng quát cho video TikTok."""
    id = scrapy.Field()
    video_url = scrapy.Field()
    webVideoUrl = scrapy.Field()
    text = scrapy.Field()
    caption = scrapy.Field()
    author = scrapy.Field()
    scraped_at = scrapy.Field()
    createTimeISO = scrapy.Field()
    duration = scrapy.Field()
    source_type = scrapy.Field()
    source_tag = scrapy.Field()
