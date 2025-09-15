from __future__ import absolute_import, unicode_literals
from celery import shared_task
import logging

logger = logging.getLogger(__name__)

import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

@shared_task
def sample_task(x, y):
    """A simple task that adds two numbers."""
    result = x + y
    logger.info(f"Adding {x} + {y} = {result}")
    return result