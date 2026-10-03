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
    scraped_at = scrapy.Field()
    source_type = scrapy.Field()
