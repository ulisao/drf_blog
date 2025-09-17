import redis
from rest_framework_api.views import StandardAPIView
from django.conf import settings
from rest_framework.exceptions import APIException, NotFound
from core.permissions import HasValidAPIKey
from django.core.cache import cache
from django.db.models import Q, F, Prefetch
from .models import CategoryAnalytics, Heading, Post, PostAnalytics, Category
from .serializers import (
    HeadingSerializer,
    PostListSerializer,
    PostSerializer,
    CategoryListSerializer,
    CategorySerializer,
)
import uuid
from django.shortcuts import get_object_or_404
from .tasks import increment_post_impressions, increment_post_views
from .utils import get_client_ip

redis_client = redis.StrictRedis(host=settings.REDIS_HOST, port=6379, db=0)

class PostListView(StandardAPIView):
    permission_classes = [HasValidAPIKey]
    
    def get(self, request, *args, **kwargs):
        try:

            search = request.query_params.get("search", "").strip()
            sorting = request.query_params.get("sorting", None)
            ordering = request.query_params.get("ordering", None)
            categories = request.query_params.getlist("categories", None)
            page = request.query_params.get("p", 1)
            
            
            # verify if posts are in cache
            cache_key = f'post_list:{search}:{sorting}:{ordering}:{categories}:{page}'
            cached_post = cache.get(cache_key)
            
            if cached_post:
                
                cached_post = [
                    post for post in cached_post if search.lower() in post['title'].lower() or
                    search.lower() in post['description'].lower() or
                    search.lower() in post['content'].lower() or
                    search.lower() in post['keywords'].lower()
                ]

                serialized_posts = PostListSerializer(cached_post, many=True).data
                
                return self.paginate(request ,cached_post)
            
            # initial empty queryset
            posts = Post.postobjects.all().select_related('category').prefetch_related(Prefetch("post_analytics", to_attr="analytics_cache"))
            
            if not posts.exists():
                raise NotFound(detail="No posts found")
            
            # If not in cache, fetch from database
            if search != "":
                posts = Post.postobjects.filter(
                    Q(title__icontains=search) | 
                    Q(description__icontains=search) | 
                    Q(content__icontains=search) |
                    Q(keywords__icontains=search)
                )
                
            # filter by categories
            if categories:
                category_queries = Q()
                for category in categories:
                    try:
                        uuid.UUID(category)
                        uuid_query = Q(category__id=category)
                        category_queries |= uuid_query
                    except ValueError:
                        slug_query = Q(category__slug=category)
                        category_queries |= slug_query
                posts = posts.filter(category_queries).distinct()

            #aplly sorting
            if sorting:
                if sorting == "newest":
                    posts = posts.order_by("-created_at")
                elif sorting == "recently_updated":
                    posts = posts.order_by("-updated_at")
                elif sorting == "oldest":
                    posts = posts.order_by("created_at")
                elif sorting == "most_viewed":
                    posts = posts.annotate(popularity=F("analytics_cache__views")).order_by("-popularity")
                            
            #aplly ordering
            if ordering:
                if ordering == "asc":
                    posts = posts.order_by("title")
                elif ordering == "desc":
                    posts = posts.order_by("-title")        
                    
            # save to cache
            cache.set(cache_key, posts, timeout=60 * 5)  # Cache for 5 minutes

            # serialize posts
            serialized_posts = PostListSerializer(posts, many=True).data
            
            # Increment impressions for each post in the cached list
            for post in cached_post:
                redis_client.incr(f"post:impressions:{post.id}")
            
            return self.paginate(request, serialized_posts)
        
        except Exception as e:
            raise APIException(detail=str(e))

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

class CategoryListView(StandardAPIView):
    permission_classes = [HasValidAPIKey]
    
    def get(self, request):
        
        try:
            parent_slug = request.query_params.get("parent_slug", None)
            search = request.query_params.get("search", "").strip()
            page = request.query_params.get("p", 1)
            sorting = request.query_params.get("sorting", None)
            ordering = request.query_params.get("ordering", None)


            cache_key = f'category_list:{page}:{search}:{sorting}:{ordering}:{parent_slug}'
            cached_categories = cache.get(cache_key)

            if cached_categories:
                serialized_cateogries = CategoryListSerializer(cached_categories, many=True).data
                
                for category in cached_categories:
                    redis_client.incr(f"category:impressions:{category.id}")
                return self.paginate(request, serialized_cateogries)

            if parent_slug:
                categories = Category.objects.filter(parent__slug=parent_slug).prefetch_related(Prefetch("category_analytics", to_attr="analytics_cache"))
            else:
                categories = Category.objects.filter(parent__isnull=True).prefetch_related(Prefetch("category_analytics", to_attr="analytics_cache"))
            
            if not categories.exists():
                raise NotFound(detail="No categories found")

            # If not in cache, fetch from database
            if search != "":
                categories = categories.filter(
                    Q(title__icontains=search) | 
                    Q(name__icontains=search) |
                    Q(slug__icontains=search) |
                    Q(description__icontains=search) 
                )
                
            #aplly sorting
            if sorting:
                if sorting == "newest":
                    posts = posts.order_by("-created_at")
                elif sorting == "recently_updated":
                    posts = posts.order_by("-updated_at")
                elif sorting == "oldest":
                    posts = posts.order_by("created_at")
                elif sorting == "most_viewed":
                    posts = posts.annotate(popularity=F("analytics_cache__views")).order_by("-popularity")
            
            #aplly ordering
            if ordering:
                if ordering == "asc":
                    posts = posts.order_by("name")
                elif ordering == "desc":
                    posts = posts.order_by("-name")        
                                  
            
            cache.set(cache_key, categories, timeout=60 * 5)
            
            serialized_cateogries = CategoryListSerializer(categories, many=True).data
            
            for category in categories:
                redis_client.incr(f"category:impressions:{category.id}")

        except Exception as e:
            raise APIException(detail=str(e))
               
class IncrementCategoryClickView(StandardAPIView):
    permission_classes = [HasValidAPIKey]

    def post(self, request):
        """Incrementa el contador de clics de un categoria basado en su slug."""

        data = request.data

        try:
            category = Category.objects.get(slug=data["slug"])
        except Category.DoesNotExist:
            raise NotFound(detail="The requested category does not exist")

        try:
            category_analytics, created = CategoryAnalytics.objects.get_or_create(category=category)
            category_analytics.increment_click()
        except Exception as e:
            raise APIException(
                detail=f"An error ocurred while updating category analytics: {str(e)}"
            )

        return self.response(
            {
                "message": "Click incremented successfully",
                "clicks": category_analytics.clicks,
            }
        )

class CategoryDetailView(StandardAPIView):
    permission_classes = [HasValidAPIKey]
    
    def get(self, request):
        
        try:
            slug = request.query_params.get("slug", None)
            page = request.query_params.get("p", 1)
            
            if not slug:
                raise self.error(detail="Category slug is required")
            
            #construir cache key
            cache_key = f'category_post:{slug}:{page}'
            cached_post = cache.get(cache_key)
            
            if cached_post:

                serialized_posts = PostListSerializer(cached_post, many=True).data
                
                for post in cached_post:
                    redis_client.incr(f"post:impressions:{post.id}")
                return self.paginate(request ,cached_post)
            
            #obtener categoria por slug
            category = get_object_or_404(Category, slug=slug)
            
            #obtener posts de la categoria
            posts = Post.postobjects.filter(category=category).select_related('category').prefetch_related(Prefetch("post_analytics", to_attr="analytics_cache"))
            
            if not posts.exists():
                raise NotFound(detail="No posts found in this category")
            
            cache.set(cache_key, posts, timeout=60 * 5)
            
            #serializar posts
            serialized_posts = PostListSerializer(posts, many=True).data
            
            for post in posts:
                    redis_client.incr(f"post:impressions:{post.id}")
            
            return self.paginate(request, serialized_posts)
        
        except Exception as e:
            raise APIException(detail=str(e))