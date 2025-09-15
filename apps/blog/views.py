import redis
from rest_framework_api.views import StandardAPIView
from django.conf import settings
from rest_framework.exceptions import APIException, NotFound
from core.permissions import HasValidAPIKey
from rest_framework.response import Response
from rest_framework.views import APIView
from django.utils.decorators import method_decorator
from django.views.decorators.cache import cache_page
from django.core.cache import cache
from .models import Heading, Post, PostAnalytics
from .serializers import (
    HeadingSerializer,
    PostListSerializer,
    PostSerializer,
)
from .tasks import increment_post_impressions, increment_post_views
from .utils import get_client_ip

redis_client = redis.StrictRedis(host=settings.REDIS_HOST, port=6379, db=0)

class PostListView(StandardAPIView):
    permission_classes = [HasValidAPIKey]
    
    def get(self, request, *args, **kwargs):
        try:
            # verify if posts are in cache
            cached_post = cache.get('post_list')
            if cached_post:
                # Increment impressions for each post in the cached list
                for post in cached_post:
                    redis_client.incr(f"post:impressions:{post.id}")
                return self.paginate(request ,cached_post)
            
            # If not in cache, fetch from database
            posts = Post.postobjects.all()

            if not posts.exists():
                raise NotFound(detail="No posts found")

            # serialize posts
            serialized_posts = PostListSerializer(posts, many=True).data
            
            # save to cache
            cache.set('post_list', serialized_posts, timeout=60 * 5)  # Cache for 5 minutes
            

        except Post.DoesNotExist:
            raise NotFound(detail="No posts found")

        except Exception as e:
            raise APIException(detail=str(e))

        return self.paginate(request, serialized_posts)

class PostDetailView(StandardAPIView):
    permission_classes = [HasValidAPIKey]
    
    def get(self, request):
        
        ip_address = get_client_ip(request)

        slug = request.query_params.get("slug")

        try:
            #Verify if post is in cache
            cached_post = cache.get(f'post_detail:{slug}')
            if cached_post:
                # Increment impressions for the cached post
                increment_post_views.delay(cached_post['slug'], ip_address)
                return self.response(cached_post)

            # If not in cache, fetch from database
            post = Post.postobjects.get(slug=slug)
            serialized_post = PostSerializer(post).data    
            
            # Save to cache
            cache.set(f'post_detail:{slug}', serialized_post, timeout=60 * 5)  # Cache for 5 minutes
            
            increment_post_views.delay(post.slug, ip_address)
            
        except Post.DoesNotExist:
            raise NotFound(
                detail="The requested article is not available or does not exist"
            )
        except Exception as e:
            raise APIException(detail=str(e))

        return self.response(serialized_post)

class PostHeadingsView(StandardAPIView):
    permission_classes = [HasValidAPIKey]
    
    def get(self, request):
        
        post_slug = request.query_params.get("slug")
        heading_objects = Heading.objects.filter(post__slug=post_slug)
        serialized_data = HeadingSerializer(heading_objects, many=True).data

        return self.response(serialized_data)

class IncrementPostClickView(StandardAPIView):
    permission_classes = [HasValidAPIKey]

    def post(self, request):
        """Incrementa el contador de clics de un post basado en su slug."""

        data = request.data

        try:
            post = Post.postobjects.get(slug=data["slug"])
        except Post.DoesNotExist:
            raise NotFound(detail="The requested post does not exist")

        try:
            post_analytics, created = PostAnalytics.objects.get_or_create(post=post)
            post_analytics.increment_click()
        except Exception as e:
            raise APIException(
                detail=f"An error ocurred while updating post analytics: {str(e)}"
            )

        return self.response(
            {
                "message": "Click incremented successfully",
                "clicks": post_analytics.clicks,
            }
        )
