from celery import shared_task
import logging
from .models import PostAnalytics, Post
import redis
from django.conf import settings

logger = logging.getLogger(__name__)

redis_client = redis.StrictRedis(host=settings.REDIS_HOST, port=6379, db=0)

@shared_task
def increment_post_impressions(post_id):
  try:
    analytics, created = PostAnalytics.objects.get_or_create(post__id=post_id)
    analytics.increment_impression()
  except Exception as e:
    logger.error(f"Error incrementing impressions for post {post_id}: {e}")
    
@shared_task
def sync_impressions_to_db():
  # Aggregate all impression counts from Redis and update the database
  
    keys = redis_client.keys("post:impressions:*")
    for key in keys:
      try:
        post_id = key.decode("utf-8").split(":")[-1]
        impressions = int(redis_client.get(key))
        
        analytics, _ = PostAnalytics.objects.get_or_create(post__id=post_id)
        analytics.impressions += impressions
        analytics.save()
        analytics._update_click_through_rate()
        
        redis_client.delete(key)
      except Exception as e:
        logger.error(f"Error syncing impressions to DB: {e}")
        
@shared_task
def increment_post_views(slug, ip_address):
  try:
    post = Post.objects.get(slug=slug)
    post_analytics, _ = PostAnalytics.objects.get_or_create(post=post)
    post_analytics.increment_view(ip_address)
  except Exception as e:
    logger.error(f"Error incrementing views for post {slug}: {e}")