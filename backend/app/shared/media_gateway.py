"""Read-only adapter for camera streams already published to local MediaMTX.

Never forwards arbitrary camera addresses, credentials, upstream cookies or
redirects to the browser. Manifests and segments stay under their Source URL.
"""
import ipaddress
import re
from urllib.parse import quote, unquote, urljoin, urlsplit
import httpx
from .errors import Error
from .security import camera_address

MAX_MEDIA_BYTES = 16 * 1024 * 1024


class MediaGateway:
    def __init__(self, config, transport=None):
        self.config = config
        self.api = self.local_base(config.media_gateway_api_url)
        self.hls = self.local_base(config.media_gateway_hls_url)
        self.http = httpx.Client(transport=transport, trust_env=False,
                                 follow_redirects=False, timeout=httpx.Timeout(10, connect=1))

    @staticmethod
    def local_base(value):
        parts = urlsplit(value)
        if (parts.scheme != 'http' or not parts.hostname or parts.username or parts.password
                or parts.path not in ('', '/') or parts.query or parts.fragment):
            raise ValueError('Media gateway must be a loopback HTTP origin')
        try:
            loopback = ipaddress.ip_address(parts.hostname).is_loopback
        except ValueError:
            loopback = parts.hostname == 'localhost'
        if not loopback:
            raise ValueError('Media gateway must listen on loopback')
        return value.rstrip('/')

    def close(self):
        self.http.close()

    def health(self):
        try:
            response = self.http.get(self.api + '/v3/paths/list', timeout=.5)
            return response.status_code == 200 and isinstance(response.json().get('items'), list)
        except (httpx.HTTPError, ValueError, AttributeError):
            return False

    @staticmethod
    def asset(value):
        if (not value or len(value) > 512 or not re.fullmatch(r'[A-Za-z0-9_./-]+', value)
                or any(piece in ('', '.', '..') for piece in value.split('/'))):
            raise Error(502, 'media_gateway_invalid', '媒体服务返回了无效的资源路径。')
        return value

    def path_for_source(self, source, networks):
        address, _, _ = camera_address(source.address, networks)
        parts = urlsplit(address)
        try:
            local = ipaddress.ip_address(parts.hostname).is_loopback
        except ValueError:
            local = parts.hostname == 'localhost'
        if not local or parts.scheme != 'rtsp' or (parts.port or 554) != self.config.media_gateway_rtsp_port:
            raise Error(503, 'media_source_not_published',
                        '该摄像头尚未发布到本机媒体网关，请先接入 MediaMTX，再使用它提供的 RTSP 地址。', retryable=True)
        path = self.asset(parts.path.lstrip('/'))
        return path

    def ensure_published(self, source, networks):
        path = self.path_for_source(source, networks)
        try:
            response = self.http.get(self.api + '/v3/paths/get/' + quote(path, safe=''), timeout=1)
            ready = response.status_code == 200 and response.json().get('ready') is True
        except (httpx.HTTPError, ValueError, AttributeError):
            ready = False
        if not ready:
            raise Error(503, 'dependency_unavailable', '媒体网关不可用或该路视频尚未就绪，请确认媒体服务与推流已启动。', retryable=True)
        return path

    def reference(self, path, asset, reference, prefix=None):
        parts = urlsplit(reference)
        decoded = unquote(parts.path)
        if (parts.fragment or '%' in decoded or '\\' in decoded
                or any(piece in ('.', '..') for piece in decoded.split('/'))
                or any(ord(char) < 32 for char in reference)):
            raise Error(502, 'media_gateway_invalid', '媒体服务返回了无效的资源引用。')
        target = urlsplit(urljoin(self.hls + '/' + path + '/' + asset, reference))
        base = urlsplit(self.hls)
        root = '/' + path + '/'
        if target.scheme != base.scheme or target.netloc != base.netloc or not target.path.startswith(root):
            raise Error(502, 'media_gateway_invalid', '媒体服务返回了越界的资源引用。')
        relative = self.asset(target.path[len(root):])
        query = ('?' + target.query) if target.query else ''
        if prefix is not None:
            return prefix + quote(relative, safe='/._-') + query
        return self.hls + root + relative + query

    def read(self, source, networks, asset, prefix, query='', range_header=None):
        # Each request rechecks Source scope and network policy, including archive.
        path = self.ensure_published(source, networks)
        asset = self.asset(asset)
        suffix = asset.rsplit('.', 1)[-1]
        types = {'m3u8':'application/vnd.apple.mpegurl', 'mp4':'video/mp4',
                 'm4s':'video/mp4', 'ts':'video/mp2t', 'aac':'audio/aac'}
        if suffix not in types:
            raise Error(404, 'media_missing', '媒体资源不存在。')
        url = self.reference(path, asset, asset.rsplit('/', 1)[-1] + ('?' + query if query else ''))
        headers = {'Range':range_header} if range_header else {}
        try:
            for _ in range(4):
                with self.http.stream('GET', url, headers=headers) as response:
                    if response.status_code in (301, 302, 303, 307, 308):
                        # MediaMTX can redirect once to check its HLS cookie.
                        url = self.reference(path, asset, response.headers.get('location', ''))
                        continue
                    if response.status_code == 404:
                        raise Error(404, 'media_missing', '媒体分片已过期或不存在，请重新打开预览。', retryable=True)
                    if response.status_code not in (200, 206):
                        raise Error(503, 'dependency_unavailable', '媒体网关暂时无法提供画面，请稍后重试。', retryable=True)
                    content = bytearray()
                    for block in response.iter_bytes():
                        content.extend(block)
                        if len(content) > MAX_MEDIA_BYTES:
                            raise Error(502, 'media_gateway_invalid', '媒体资源超过允许的大小。')
                    body = bytes(content)
                    if suffix == 'm3u8':
                        text = body.decode('utf8')
                        if not text.startswith('#EXTM3U'):
                            raise ValueError('Not an HLS manifest')
                        lines = []
                        for line in text.splitlines():
                            if line and not line.startswith('#'):
                                line = self.reference(path, asset, line, prefix)
                            elif line.startswith('#'):
                                line = re.sub(r'URI="([^"]+)"', lambda match:
                                    'URI="' + self.reference(path, asset, match[1], prefix) + '"', line)
                            lines.append(line)
                        body = ('\n'.join(lines) + '\n').encode()
                    result_headers = {'Cache-Control':'no-store'}
                    for name in ('content-range', 'accept-ranges'):
                        if name in response.headers:
                            result_headers[name] = response.headers[name]
                    return body, response.status_code, types[suffix], result_headers
            raise Error(502, 'media_gateway_invalid', '媒体服务重定向次数过多。')
        except (httpx.HTTPError, UnicodeError, ValueError):
            raise Error(503, 'dependency_unavailable', '媒体网关连接中断，请稍后重试。', retryable=True)
