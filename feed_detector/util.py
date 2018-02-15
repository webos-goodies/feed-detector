# -*- coding: utf-8 -*-

from __future__ import absolute_import, division, print_function, unicode_literals

import re

__all__ = ('LINK_MATCH', 'is_valid_url')


LINK_MATCH = re.compile(r'\s*https?://', re.I).match
DENY_MATCH = re.compile(r'adclick\.g\.doubleclick\.net/'
                        r'|googleads\.g\.doubleclick\.net/'
                        r'|rd\.ane\.yahoo\.co\.jp/'
                        r'|paid\.outbrain\.com/network/redir'
                        r'|a\.popin\.cc/popin_redirect/'
                        r'|click\.linksynergy\.com/'
                        r'|www\.facebook\.com/sharer/sharer.php'
                        r'|twitter\.com/intent/tweet'
                        r'|twitter\.com/share'
                        r'|adserver\.adtechjp\.com/'
                        r'|tg\.socdm\.com/rd'
                        r'|s-adserver\.cxad\.cxense\.com/'
                        r'|nkis\.nikkei\.com/pub_click/'
                        r'|2ch-c\.net/'
                        r'|dsp\.logly\.co\.jp/click\?ad='
                        r'|ac\.ebis\.ne\.jp/'
                        r'|af\.moshimo\.com/'
                        r'|tr\.adgocoo\.com/'
                        r'|[^w][^.]+\.i-mobile\.co\.jp/'
                        r'|[^.]+\.[^.]+\.impact-ad\.jp/'
                        , re.I).match

def is_valid_url(s):
    m = LINK_MATCH(s)
    return m and not DENY_MATCH(s, m.end())
