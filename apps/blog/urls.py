from django.urls import path
from .views import PostListView, PostDetailView, PostHeadingsView, CategoryListView, IncrementCategoryClickView, IncrementPostClickView, CategoryDetailView



urlpatterns = [
  path('posts/', PostListView.as_view(), name='post-list'),
  path('post/', PostDetailView.as_view(), name='post-detail'),
  path('post/headings/', PostHeadingsView.as_view(), name='post-headings'),
  path('post/increment_click/', IncrementPostClickView.as_view(), name='increment-post-click'),
  path('categories/', CategoryListView.as_view(), name='category-list'),
  path('categories/increment_click/', IncrementCategoryClickView.as_view(), name='increment-category-click'),
  path('category/posts/', CategoryDetailView.as_view(), name='category-posts'),
]