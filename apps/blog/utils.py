def get_client_ip(request):
    # Get client IP address from request
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    # If there are multiple IPs, take the first one
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0]
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip