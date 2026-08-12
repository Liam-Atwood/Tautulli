# -*- coding: utf-8 -*-

import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


_SECRET_KEYS = frozenset({
    'access_token', 'api_key', 'apikey', 'authorization', 'token', 'x-emby-token',
    'x-mediabrowser-token', 'x-plex-token',
})


def _redact(value):
    if value is None:
        return None
    text = str(value)
    try:
        parts = urlsplit(text)
    except ValueError:
        return text
    if parts.query:
        query = [
            (key, '<redacted>' if key.lower() in _SECRET_KEYS else item)
            for key, item in parse_qsl(parts.query, keep_blank_values=True)
        ]
        text = urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))
    secret_names = '|'.join(re.escape(key) for key in sorted(_SECRET_KEYS, key=len, reverse=True))
    pattern = r'(?i)\b({})\b(\s*[:=]\s*)([^\s,;&]+)'.format(secret_names)
    return re.sub(pattern, r'\1\2<redacted>', text)


class BackendError(Exception):
    """Base error with context safe for logs and user-facing diagnostics."""

    def __init__(self, message, endpoint=None, status_code=None, retry_after=None):
        super().__init__(message)
        self.message = _redact(message)
        self.endpoint = _redact(endpoint)
        self.status_code = status_code
        self.retry_after = retry_after

    def __str__(self):
        context = []
        if self.endpoint:
            context.append('endpoint={}'.format(self.endpoint))
        if self.status_code is not None:
            context.append('status={}'.format(self.status_code))
        if self.retry_after is not None:
            context.append('retry_after={}'.format(self.retry_after))
        return '{}{}'.format(self.message, ' ({})'.format(', '.join(context)) if context else '')


class BackendConfigurationError(BackendError):
    pass


class BackendConnectionError(BackendError):
    pass


class BackendAuthError(BackendError):
    pass


class BackendNotFoundError(BackendError):
    pass


class BackendRateLimitError(BackendError):
    pass


class BackendServerError(BackendError):
    pass


class BackendFeatureUnsupportedError(BackendError):
    pass
