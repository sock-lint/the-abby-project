from celery import shared_task


@shared_task
def prune_usage_events():
    from .services import prune_usage_data
    return prune_usage_data()
