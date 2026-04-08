class PrivateNetworkAccessMiddleware:
    """Adds CORS Access-Control-Allow-Private-Network header on PNA preflights.

    Chrome sends `Access-Control-Request-Private-Network: true` on OPTIONS
    preflights when a public-origin page calls a private-network target
    (e.g. abby.bos.lol → 192.168.x.x). The response must echo
    `Access-Control-Allow-Private-Network: true` or the fetch is blocked.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if (
            request.method == "OPTIONS"
            and request.META.get("HTTP_ACCESS_CONTROL_REQUEST_PRIVATE_NETWORK", "").lower() == "true"
        ):
            response["Access-Control-Allow-Private-Network"] = "true"
        return response
