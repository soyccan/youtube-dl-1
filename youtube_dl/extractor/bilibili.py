# coding: utf-8
from __future__ import unicode_literals

import hashlib
import re
import json

from .common import InfoExtractor
from ..compat import (
    compat_parse_qs,
    compat_urlparse,
)
from ..utils import (
    ExtractorError,
    int_or_none,
    float_or_none,
    parse_iso8601,
    smuggle_url,
    str_or_none,
    strip_jsonp,
    unified_timestamp,
    unsmuggle_url,
    urlencode_postdata,
)


class BiliBiliIE(InfoExtractor):
    _VALID_URL = r'''(?x)
                    https?://
                        (?:(?:www|bangumi)\.)?
                        bilibili\.(?:tv|com)/
                        (?:
                            (?:
                                video/[aA][vV]|
                                anime/(?P<anime_id>\d+)/play\#
                            )(?P<id_bv>\d+)|
                            video/[bB][vV](?P<id>[^/?#&]+)
                        )
                        \?p=(?P<page>\d+)
                    '''

    # new test, full anime: https://www.bilibili.com/bangumi/play/ss28685/
    # new test, anime single episode: https://www.bilibili.com/bangumi/play/ep285921
    # new test, video: https://www.bilibili.com/video/av58781780
    # new test, video with pages: https://www.bilibili.com/video/av11849?p=2
    # new test, video with pages: https://www.bilibili.com/video/BV1ms411F7E1?p=2
    _TESTS = [{
        'url': 'http://www.bilibili.tv/video/av1074402/',
        'md5': '5f7d29e1a2872f3df0cf76b1f87d3788',
        'info_dict': {
            'id': '1074402',
            'ext': 'flv',
            'title': '【金坷垃】金泡沫',
            'description': 'md5:ce18c2a2d2193f0df2917d270f2e5923',
            'duration': 308.067,
            'timestamp': 1398012678,
            'upload_date': '20140420',
            'thumbnail': r're:^https?://.+\.jpg',
            'uploader': '菊子桑',
            'uploader_id': '156160',
        },
    }, {
        # Tested in BiliBiliBangumiIE
        'url': 'http://bangumi.bilibili.com/anime/1869/play#40062',
        'only_matching': True,
    }, {
        'url': 'http://bangumi.bilibili.com/anime/5802/play#100643',
        'md5': '3f721ad1e75030cc06faf73587cfec57',
        'info_dict': {
            'id': '100643',
            'ext': 'mp4',
            'title': 'CHAOS;CHILD',
            'description': '如果你是神明，并且能够让妄想成为现实。那你会进行怎么样的妄想？是淫靡的世界？独裁社会？毁灭性的制裁？还是……2015年，涩谷。从6年前发生的大灾害“涩谷地震”之后复兴了的这个街区里新设立的私立高中...',
        },
        'skip': 'Geo-restricted to China',
    }, {
        # Title with double quotes
        'url': 'http://www.bilibili.com/video/av8903802/',
        'info_dict': {
            'id': '8903802',
            'title': '阿滴英文｜英文歌分享#6 "Closer',
            'description': '滴妹今天唱Closer給你聽! 有史以来，被推最多次也是最久的歌曲，其实歌词跟我原本想像差蛮多的，不过还是好听！ 微博@阿滴英文',
        },
        'playlist': [{
            'info_dict': {
                'id': '8903802_part1',
                'ext': 'flv',
                'title': '阿滴英文｜英文歌分享#6 "Closer',
                'description': 'md5:3b1b9e25b78da4ef87e9b548b88ee76a',
                'uploader': '阿滴英文',
                'uploader_id': '65880958',
                'timestamp': 1488382634,
                'upload_date': '20170301',
            },
            'params': {
                'skip_download': True,  # Test metadata only
            },
        }, {
            'info_dict': {
                'id': '8903802_part2',
                'ext': 'flv',
                'title': '阿滴英文｜英文歌分享#6 "Closer',
                'description': 'md5:3b1b9e25b78da4ef87e9b548b88ee76a',
                'uploader': '阿滴英文',
                'uploader_id': '65880958',
                'timestamp': 1488382634,
                'upload_date': '20170301',
            },
            'params': {
                'skip_download': True,  # Test metadata only
            },
        }]
    }]

    _APP_KEY = 'iVGUTjsxvpLeuDCf'
    _BILIBILI_KEY = 'aHRmhWMLkdeMuILqORnYZocwMBpMEOdt'

    def _report_error(self, result):
        if 'message' in result:
            raise ExtractorError('%s said: %s' % (self.IE_NAME, result['message']), expected=True)
        elif 'code' in result:
            raise ExtractorError('%s returns error %d' % (self.IE_NAME, result['code']), expected=True)
        else:
            raise ExtractorError('Can\'t extract Bangumi episode ID')

    def _real_extract(self, url):
        url, smuggled_data = unsmuggle_url(url, {})

        mobj = re.match(self._VALID_URL, url)
        video_id = mobj.group('id')
        anime_id = mobj.group('anime_id')
        webpage = self._download_webpage(url, video_id)

        # TODO: See page as playlist index
        if 'bangumi/' not in url:
            # common video
            state_raw = re.search(r'__INITIAL_STATE__=(\{.*?\});', webpage)
            state = json.loads(state_raw.group(1))
            aid = str(state['videoData']['aid'])
            cid = str(state['videoData']['cid'])

            page = mobj.group('page')
            if page:
                cid = [ str(x['cid']) for x in state['videoData']['pages'] if str(x['page']) == page ][0]

        else:
            # anime episode
            if 'no_bangumi_tip' not in smuggled_data:
                self.to_screen('Downloading episode %s. To download all videos in anime %s, re-run youtube-dl with %s' % (
                    video_id, anime_id, compat_urlparse.urljoin(url, '//bangumi.bilibili.com/anime/%s' % anime_id)))
            headers = {
                'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
                'Referer': url
            }
            headers.update(self.geo_verification_headers())

            state_raw = re.search(r'__INITIAL_STATE__=(\{.*?\});', webpage)
            state = json.loads(state_raw.group(1))
            anime_id = str(state['mediaInfo']['id'])

            cid = [ str(x['cid']) for x in state['epList'] if str(x['id']) == video_id ][0]
            aid = [ str(x['aid']) for x in state['epList'] if str(x['id']) == video_id ][0]

        headers = {
            'Referer': url
        }
        headers.update(self.geo_verification_headers())

        entries = []

        # Reference: https://greasyfork.org/zh-TW/scripts/372516-bilibili-merged-flv-mp4-ass-enhance
        # const isBangumi = location.pathname.includes("bangumi") || location.hostname.includes("bangumi")
        # const apiPath = isBangumi ? "/pgc/player/web/playurl" : "/x/player/playurl"
        # const qn = (monkey.option.enableVideoMaxResolution && monkey.option.videoMaxResolution) || "120"
        # const api_url = `https://api.bilibili.com${apiPath}?avid=${aid}&cid=${cid}&otype=json&qn=${qn}`

        isBangumi = 'bangumi' in url
        apiPath = '/pgc/player/web/playurl' if isBangumi else '/x/player/playurl'
        RENDITIONS = ('qn=120', 'qn=80&quality=80&type=', 'quality=2&type=mp4')
        for num, rendition in enumerate(RENDITIONS, start=1):
            api_url = f'https://api.bilibili.com{apiPath}?avid={aid}&cid={cid}&otype=json&{rendition}'
            video_info = self._download_json(api_url, video_id)

            if not video_info:
                continue
            elif isBangumi:
                video_info = video_info['result']
            else:
                video_info = video_info['data']

            if 'durl' not in video_info:
                if num < len(RENDITIONS):
                    continue
                self._report_error(video_info)

            for idx, durl in enumerate(video_info['durl']):
                formats = [{
                    'url': durl['url'],
                    'filesize': int_or_none(durl['size']),
                }]
                if durl.get('backup_url'):
                    for backup_url in durl.get('backup_url', []):
                        formats.append({
                            'url': backup_url,
                            # backup URLs have lower priorities
                            'preference': -2 if 'hd.mp4' in backup_url else -3,
                        })

                for a_format in formats:
                    a_format.setdefault('http_headers', {}).update({
                        'Referer': url,
                    })

                self._sort_formats(formats)

                entries.append({
                    'id': '%s_part%s' % (video_id, idx),
                    'duration': float_or_none(durl.get('length'), 1000),
                    'formats': formats,
                })
            break

        title = self._html_search_regex(
            ('<h1[^>]+\btitle=(["\'])(?P<title>(?:(?!\1).)+)\1',
             '(?s)<h1[^>]*>(?P<title>.+?)</h1>'), webpage, 'title',
            group='title')
        description = self._html_search_meta('description', webpage)
        timestamp = unified_timestamp(self._html_search_regex(
            r'<time[^>]+datetime="([^"]+)"', webpage, 'upload time',
            default=None) or self._html_search_meta(
            'uploadDate', webpage, 'timestamp', default=None))
        thumbnail = self._html_search_meta(['og:image', 'thumbnailUrl'], webpage)

        # TODO 'view_count' requires deobfuscating Javascript
        info = {
            'id': video_id,
            'title': title,
            'description': description,
            'timestamp': timestamp,
            'thumbnail': thumbnail,
            'duration': float_or_none(video_info.get('timelength'), scale=1000),
        }

        uploader_mobj = re.search(
            r'<a[^>]+href="(?:https?:)?//space\.bilibili\.com/(?P<id>\d+)"[^>]*>(?P<name>[^<]+)',
            webpage)
        if uploader_mobj:
            info.update({
                'uploader': uploader_mobj.group('name'),
                'uploader_id': uploader_mobj.group('id'),
            })
        if not info.get('uploader'):
            info['uploader'] = self._html_search_meta(
                'author', webpage, 'uploader', default=None)

        for entry in entries:
            entry.update(info)

        if len(entries) == 1:
            return entries[0]
        else:
            for idx, entry in enumerate(entries):
                entry['id'] = '%s_part%d' % (video_id, (idx + 1))

            return {
                '_type': 'multi_video',
                'id': video_id,
                'title': title,
                'description': description,
                'entries': entries,
            }


class BiliBiliBangumiIE(InfoExtractor):
    _VALID_URL = r'https?://(bangumi|www)\.bilibili\.com/(anime/|bangumi/media/md)(?P<id>\d+)'

    IE_NAME = 'bangumi.bilibili.com'
    IE_DESC = 'BiliBili番剧'

    # new test: https://www.bilibili.com/bangumi/media/md28222851/
    _TESTS = [{
        'url': 'http://bangumi.bilibili.com/anime/1869',
        'info_dict': {
            'id': '1869',
            'title': '混沌武士',
            'description': 'md5:6a9622b911565794c11f25f81d6a97d2',
        },
        'playlist_count': 26,
    }, {
        'url': 'http://bangumi.bilibili.com/anime/1869',
        'info_dict': {
            'id': '1869',
            'title': '混沌武士',
            'description': 'md5:6a9622b911565794c11f25f81d6a97d2',
        },
        'playlist': [{
            'md5': '91da8621454dd58316851c27c68b0c13',
            'info_dict': {
                'id': '40062',
                'ext': 'mp4',
                'title': '混沌武士',
                'description': '故事发生在日本的江户时代。风是一个小酒馆的打工女。一日，酒馆里来了一群恶霸，虽然他们的举动令风十分不满，但是毕竟风只是一届女流，无法对他们采取什么行动，只能在心里嘟哝。这时，酒家里又进来了个“不良份子...',
                'timestamp': 1414538739,
                'upload_date': '20141028',
                'episode': '疾风怒涛 Tempestuous Temperaments',
                'episode_number': 1,
            },
        }],
        'params': {
            'playlist_items': '1',
        },
    }]

    @classmethod
    def suitable(cls, url):
        return False if BiliBiliIE.suitable(url) else super(BiliBiliBangumiIE, cls).suitable(url)

    def _real_extract(self, url):
        bangumi_id = self._match_id(url)

        # Sometimes this API returns a JSONP response
        season_info = self._download_json(
            'http://bangumi.bilibili.com/jsonp/seasoninfo/%s.ver' % bangumi_id,
            bangumi_id, transform_source=strip_jsonp)['result']

        entries = [{
            '_type': 'url_transparent',
            'url': smuggle_url(episode['webplay_url'], {'no_bangumi_tip': 1}),
            'ie_key': BiliBiliIE.ie_key(),
            'timestamp': parse_iso8601(episode.get('update_time'), delimiter=' '),
            'episode': episode.get('index_title'),
            'episode_number': int_or_none(episode.get('index')),
        } for episode in season_info['episodes']]

        entries = sorted(entries, key=lambda entry: entry.get('episode_number'))

        return self.playlist_result(
            entries, bangumi_id,
            season_info.get('bangumi_title'), season_info.get('evaluate'))


class BilibiliAudioBaseIE(InfoExtractor):
    def _call_api(self, path, sid, query=None):
        if not query:
            query = {'sid': sid}
        return self._download_json(
            'https://www.bilibili.com/audio/music-service-c/web/' + path,
            sid, query=query)['data']


class BilibiliAudioIE(BilibiliAudioBaseIE):
    _VALID_URL = r'https?://(?:www\.)?bilibili\.com/audio/au(?P<id>\d+)'
    _TEST = {
        'url': 'https://www.bilibili.com/audio/au1003142',
        'md5': 'fec4987014ec94ef9e666d4d158ad03b',
        'info_dict': {
            'id': '1003142',
            'ext': 'm4a',
            'title': '【tsukimi】YELLOW / 神山羊',
            'artist': 'tsukimi',
            'comment_count': int,
            'description': 'YELLOW的mp3版！',
            'duration': 183,
            'subtitles': {
                'origin': [{
                    'ext': 'lrc',
                }],
            },
            'thumbnail': r're:^https?://.+\.jpg',
            'timestamp': 1564836614,
            'upload_date': '20190803',
            'uploader': 'tsukimi-つきみぐー',
            'view_count': int,
        },
    }

    def _real_extract(self, url):
        au_id = self._match_id(url)

        play_data = self._call_api('url', au_id)
        formats = [{
            'url': play_data['cdns'][0],
            'filesize': int_or_none(play_data.get('size')),
        }]

        song = self._call_api('song/info', au_id)
        title = song['title']
        statistic = song.get('statistic') or {}

        subtitles = None
        lyric = song.get('lyric')
        if lyric:
            subtitles = {
                'origin': [{
                    'url': lyric,
                }]
            }

        return {
            'id': au_id,
            'title': title,
            'formats': formats,
            'artist': song.get('author'),
            'comment_count': int_or_none(statistic.get('comment')),
            'description': song.get('intro'),
            'duration': int_or_none(song.get('duration')),
            'subtitles': subtitles,
            'thumbnail': song.get('cover'),
            'timestamp': int_or_none(song.get('passtime')),
            'uploader': song.get('uname'),
            'view_count': int_or_none(statistic.get('play')),
        }


class BilibiliAudioAlbumIE(BilibiliAudioBaseIE):
    _VALID_URL = r'https?://(?:www\.)?bilibili\.com/audio/am(?P<id>\d+)'
    _TEST = {
        'url': 'https://www.bilibili.com/audio/am10624',
        'info_dict': {
            'id': '10624',
            'title': '每日新曲推荐（每日11:00更新）',
            'description': '每天11:00更新，为你推送最新音乐',
        },
        'playlist_count': 19,
    }

    def _real_extract(self, url):
        am_id = self._match_id(url)

        songs = self._call_api(
            'song/of-menu', am_id, {'sid': am_id, 'pn': 1, 'ps': 100})['data']

        entries = []
        for song in songs:
            sid = str_or_none(song.get('id'))
            if not sid:
                continue
            entries.append(self.url_result(
                'https://www.bilibili.com/audio/au' + sid,
                BilibiliAudioIE.ie_key(), sid))

        if entries:
            album_data = self._call_api('menu/info', am_id) or {}
            album_title = album_data.get('title')
            if album_title:
                for entry in entries:
                    entry['album'] = album_title
                return self.playlist_result(
                    entries, am_id, album_title, album_data.get('intro'))

        return self.playlist_result(entries, am_id)
