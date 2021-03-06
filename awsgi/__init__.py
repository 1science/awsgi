from io import StringIO, BytesIO
import sys
from urllib.parse import urlencode
from functools import partial
import base64
import logging


logger = logging.getLogger('awsgi')


BINARY_ENCODINGS = [
    "gzip"
]


BINARY_CONTENT_TYPES = [
    "application/font-woff"
]


def convert_str(b64, s):
    # encodes binary data using base64
    if b64:
        return base64.b64encode(s).decode('utf-8')
    else:
        return s.decode('utf-8') if isinstance(s, bytes) else s


def _base64_encode(content_encoding, content_type):
    return content_encoding in BINARY_ENCODINGS or content_type in BINARY_CONTENT_TYPES


def response(app, event, context):
    logger.debug(f'Received event {event}')

    sr = StartResponse()
    output = app(environ(event, context), sr)
    return sr.response(output)


class StartResponse:
    def __init__(self):
        self.status = 500
        self.headers = []
        self.body = StringIO()

    def __call__(self, status, headers, exc_info=None):
        self.status = status.split()[0]
        self.headers[:] = headers
        return self.body.write

    def response(self, output):
        headers = dict(self.headers)

        content_encoding = headers.get('Content-Encoding')
        content_type = headers.get('Content-Type')
        isBase64Encoded = _base64_encode(content_encoding, content_type)

        return {
            'statusCode': str(self.status),
            'headers': dict(self.headers),
            'body': self.body.getvalue() + ''.join(map(partial(convert_str, isBase64Encoded), output)),
            'isBase64Encoded': isBase64Encoded
        }


def environ(event, context):

    request_body = event.get('body') or ''
    if event['isBase64Encoded']:
        request_body = base64.b64decode(request_body)
    else:
        request_body = request_body.encode('utf-8')

    environ = {
        'REQUEST_METHOD': event['httpMethod'],
        'SCRIPT_NAME': '',
        'PATH_INFO': event['path'],
        'QUERY_STRING': urlencode(event['queryStringParameters'] or {}),
        'REMOTE_ADDR': '127.0.0.1',
        'CONTENT_LENGTH': str(len(request_body)),
        'HTTP': 'on',
        'SERVER_PROTOCOL': 'HTTP/1.1',
        'wsgi.version': (1, 0),
        'wsgi.input': BytesIO(request_body),
        'wsgi.errors': sys.stderr,
        'wsgi.multithread': False,
        'wsgi.multiprocess': False,
        'wsgi.run_once': False
    }

    headers = event.get('headers', {})
    for k, v in headers.items():
        k = k.upper().replace('-', '_')

        if k == 'CONTENT_TYPE':
            environ['CONTENT_TYPE'] = v
        elif k == 'HOST':
            environ['SERVER_NAME'] = v
        elif k == 'X_FORWARDED_FOR':
            environ['REMOTE_ADDR'] = v.split(', ')[0]
        elif k == 'X_FORWARDED_PROTO':
            environ['wsgi.url_scheme'] = v
        elif k == 'X_FORWARDED_PORT':
            environ['SERVER_PORT'] = v

        environ['HTTP_' + k] = v.encode('ascii', 'replace').decode('ascii')

    environ['HTTP_X_1SCIENCE_CONFIG'] = event.get(
        'requestContext', {}).get('authorizer', {}).get('config')

    return environ
