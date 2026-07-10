"""폰트·이미지 로딩 유틸."""
import os
from functools import lru_cache

import pygame

# macOS / 일반 리눅스 등에서 흔한 한글 지원 폰트 후보들
_FONT_CANDIDATES = [
    "/System/Library/Fonts/AppleSDGothicNeo.ttc",
    "/System/Library/Fonts/Supplemental/AppleGothic.ttf",
    "/System/Library/Fonts/Supplemental/NotoSansGothic-Regular.ttf",
    "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "C:/Windows/Fonts/malgun.ttf",
]


def _find_font_path():
    for path in _FONT_CANDIDATES:
        if os.path.exists(path):
            return path
    return None


@lru_cache(maxsize=64)
def get_font(size, bold=False):
    """크기별 폰트를 캐시해서 돌려준다."""
    path = _find_font_path()
    if path:
        font = pygame.font.Font(path, size)
        font.set_bold(bold)
        return font
    # 최후의 수단: 시스템 폰트 이름으로 시도
    return pygame.font.SysFont("applegothic,malgungothic,arial", size, bold=bold)


_ASSET_DIR = os.path.join(os.path.dirname(__file__), "assets")
_MENU_BATTER = None
_MENU_SCENE = None


def _strip_white_background(surface, threshold=248):
    """흰 배경을 투명 처리해 실루엣만 남긴다."""
    surface = surface.convert_alpha()
    for x in range(surface.get_width()):
        for y in range(surface.get_height()):
            r, g, b, a = surface.get_at((x, y))
            if r >= threshold and g >= threshold and b >= threshold:
                surface.set_at((x, y), (r, g, b, 0))
    return surface


def _load_menu_sprite(filename, target_height):
    path = os.path.join(_ASSET_DIR, filename)
    raw = pygame.image.load(path).convert_alpha()
    raw = _strip_white_background(raw)
    w, h = raw.get_size()
    scale = target_height / h
    size = (max(1, int(w * scale)), max(1, int(h * scale)))
    return pygame.transform.smoothscale(raw, size)


def get_menu_batter(target_height=175):
    """타이틀 화면용 타자 실루엣(우측)."""
    global _MENU_BATTER
    if _MENU_BATTER is None:
        _MENU_BATTER = _load_menu_sprite("menu_batter.png", target_height)
    return _MENU_BATTER


def get_menu_scene(target_height=175):
    """타이틀 화면용 심판·포수·타자 실루엣(좌측)."""
    global _MENU_SCENE
    if _MENU_SCENE is None:
        _MENU_SCENE = _load_menu_sprite("menu_scene.png", target_height)
    return _MENU_SCENE
