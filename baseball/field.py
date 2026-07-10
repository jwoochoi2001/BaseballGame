"""하늘에서 본(탑다운) 부채꼴 야구장 렌더링과 좌표 변환.

필드 좌표계(단위: 피트):
  - 홈플레이트 = (0, 0)
  - +y = 중견수 방향(위쪽), +x = 우익수 방향(오른쪽)
  - 좌우 파울선은 홈에서 ±45도
"""
import math

import pygame

from . import config as C
from .assets import get_menu_batter, get_menu_scene

# ---------------------------------------------------------------- 필드 상수(피트)
BASE = 90.0
D = BASE / math.sqrt(2)              # 63.64
HOME = (0.0, 0.0)
B1 = (D, D)                          # 1루
B2 = (0.0, BASE * math.sqrt(2))      # 2루 (127.3)
B3 = (-D, D)                         # 3루
MOUND = (0.0, 60.5)
BASES_XY = {"1B": B1, "2B": B2, "3B": B3, "home": HOME}

FOUL_DEG = 45.0
FENCE_LINE = 330.0
FENCE_CENTER = 400.0

# 수비 기본 위치(피트)
FIELDERS_HOME = {
    "투수": (0.0, 60.5),
    "1루수": (54.0, 80.0),
    "2루수": (38.0, 128.0),
    "유격수": (-38.0, 128.0),
    "3루수": (-54.0, 80.0),
    "좌익수": (-150.0, 250.0),
    "중견수": (0.0, 315.0),
    "우익수": (150.0, 250.0),
}
CATCHER = (0.0, -9.0)
UMPIRE = (0.0, -15.0)

# ---------------------------------------------------------------- 화면 변환
SB_H = 104                       # 전광판 높이
CX = C.WIDTH // 2
HOME_SY = C.HEIGHT - 58          # 홈플레이트 화면 y
FIELD_TOP = SB_H + 12

# 외야 압축: 내야는 실측 비율, 외야는 눌러서 실제 구장처럼(외야 잔디를 작게)
_WARP_D0 = 95.0
_WARP_COMP = 0.52


def _warp(d):
    return d if d <= _WARP_D0 else _WARP_D0 + (d - _WARP_D0) * _WARP_COMP


STAND_MARGIN = 100               # 필드 위/옆 관중석 여백(px)
SCALE = (HOME_SY - FIELD_TOP - STAND_MARGIN) / _warp(FENCE_CENTER + 25)


def to_screen(x, y):
    r = math.hypot(x, y)
    if r > 1e-6:
        f = _warp(r) / r
        x, y = x * f, y * f
    return (int(CX + x * SCALE), int(HOME_SY - y * SCALE))


# ---------------------------------------------------------------- 관중석 / 스카이
_CROWD = None
_SKY = None


def _sky_surface():
    global _SKY
    if _SKY is not None:
        return _SKY
    surf = pygame.Surface((C.WIDTH, C.HEIGHT))
    split = int(C.HEIGHT * C.SKY_SPLIT)
    for y in range(C.HEIGHT):
        if y < split:
            t = y / max(1, split - 1)
            r = int(C.SKY_TOP[0] + (C.SKY[0] - C.SKY_TOP[0]) * t)
            g = int(C.SKY_TOP[1] + (C.SKY[1] - C.SKY_TOP[1]) * t)
            b = int(C.SKY_TOP[2] + (C.SKY[2] - C.SKY_TOP[2]) * t)
        else:
            t = (y - split) / max(1, C.HEIGHT - split - 1)
            r = int(C.SKY_LOWER[0] + (C.SKY_LOWER_DEEP[0] - C.SKY_LOWER[0]) * t)
            g = int(C.SKY_LOWER[1] + (C.SKY_LOWER_DEEP[1] - C.SKY_LOWER[1]) * t)
            b = int(C.SKY_LOWER[2] + (C.SKY_LOWER_DEEP[2] - C.SKY_LOWER[2]) * t)
        pygame.draw.line(surf, (r, g, b), (0, y), (C.WIDTH, y))
    _SKY = surf
    return _SKY


def _stand_r(deg):
    """해당 각도에서 담장 기준 반경."""
    return fence_dist(min(FOUL_DEG, abs(deg))) if abs(deg) <= FOUL_DEG else FENCE_LINE


CROWD_DOT_R = 5
CROWD_DOT_R_BACK = 4


def _draw_fan_dot(surface, x, y, rng, radius=CROWD_DOT_R):
    """관중 — 컬러 동그라미(머리)만."""
    shirt = rng.choice([(224, 72, 72), (72, 116, 224), (244, 204, 64), (238, 238, 240),
                        (64, 184, 96), (232, 132, 44), (176, 84, 200), (48, 194, 204)])
    pygame.draw.circle(surface, shirt, (int(x), int(y)), radius)


def _fill_stand_section(surf, rng, ang0, ang1, r0, r1, hx, hy,
                        step_deg=1.6, step_rad=0.028):
    """두 반경 사이 부채꼴 좌석에 관중을 빽빽히 채운다."""
    rad = r0
    while rad < r1:
        deg = ang0
        while deg <= ang1:
            x, y = to_screen(*polar(_stand_r(deg) * rad, deg))
            if 8 <= x < C.WIDTH - 8 and SB_H + 4 <= y < C.HEIGHT - 8:
                r = CROWD_DOT_R if rad < (r0 + r1) * 0.55 else CROWD_DOT_R_BACK
                _draw_fan_dot(surf, x, y, rng, radius=r)
            deg += step_deg
        rad += step_rad


def _draw_tier_ring(surf, ang0, ang1, mul, color, steps=48):
    ring = []
    for i in range(steps + 1):
        deg = ang0 + (ang1 - ang0) * i / steps
        ring.append(to_screen(*polar(_stand_r(deg) * mul, deg)))
    pygame.draw.lines(surf, color, False, ring, 3)


def _crowd_surface():
    """외야 관중석 2층만(내야 관중 없음), 배경은 하늘."""
    global _CROWD
    if _CROWD is not None:
        return _CROWD
    import random as _r
    surf = pygame.Surface((C.WIDTH, C.HEIGHT))
    surf.blit(_sky_surface(), (0, 0))

    rng = _r.Random(20260718)
    hx, hy = to_screen(*HOME)

    # ---- 외야 중앙 2층
    of_tiers = (1.08, 1.26)
    for i, mul in enumerate(of_tiers):
        _draw_tier_ring(surf, -36, 36, mul, C.STANDS_DARK if i else C.STANDS_RAIL)
        r0 = of_tiers[i - 1] if i > 0 else 1.04
        _fill_stand_section(surf, rng, -36, 36, r0 + 0.01, mul - 0.01, hx, hy,
                            step_deg=1.0, step_rad=0.019)

    # 외야 양쪽 2층
    for side in (-1, 1):
        a0, a1 = (-44, -20) if side < 0 else (20, 44)
        for i, mul in enumerate(of_tiers):
            _draw_tier_ring(surf, a0, a1, mul, C.STANDS_DARK if i else C.STANDS_RAIL)
            r0 = of_tiers[i - 1] if i > 0 else 1.04
            _fill_stand_section(surf, rng, a0, a1, r0 + 0.01, mul - 0.01, hx, hy,
                                step_deg=1.2, step_rad=0.020)

    _CROWD = surf
    return _CROWD


def _draw_center_scoreboard(surface):
    """중견 담장 뒤 전광판 모형(다리 지지대 포함)."""
    w, h = 220, 44
    x, y = CX - w // 2, FIELD_TOP + 20
    leg_h = 56
    leg_y = y + h
    for lx in (x + 22, x + w - 30):
        pygame.draw.rect(surface, (68, 72, 82), (lx, leg_y, 12, leg_h))
        pygame.draw.rect(surface, (52, 56, 66), (lx + 1, leg_y, 10, leg_h), 1)
    pygame.draw.rect(surface, (118, 122, 132), (x, y, w, h), border_radius=4)
    pygame.draw.rect(surface, (88, 92, 102), (x, y, w, h), width=3, border_radius=4)
    pygame.draw.rect(surface, (100, 104, 114), (x + 8, y + 8, w - 16, h - 16), border_radius=2)


def _draw_light_tower(surface, bx, by):
    """야구장 야간 조명탑."""
    pygame.draw.rect(surface, (78, 82, 92), (bx - 3, by + 10, 6, 50))
    pygame.draw.rect(surface, (62, 66, 76), (bx - 22, by, 44, 14), border_radius=3)
    for row in range(4):
        for col in range(5):
            lx = bx - 16 + col * 8
            ly = by + 3 + row * 3
            pygame.draw.circle(surface, (255, 252, 230), (lx, ly), 2)
            pygame.draw.circle(surface, (220, 210, 160), (lx, ly), 2, 1)


def polar(dist, deg):
    """홈 기준 거리/각도(0=중견수, +=우측) -> 필드 좌표."""
    r = math.radians(deg)
    return (dist * math.sin(r), dist * math.cos(r))


def fence_dist(deg):
    a = min(1.0, abs(deg) / FOUL_DEG)
    return FENCE_CENTER + (FENCE_LINE - FENCE_CENTER) * a


def spray_deg(x, y):
    return math.degrees(math.atan2(x, max(0.001, y)))


def is_foul_point(point):
    """착지·통과 지점이 파울라인(±45°) 바깥이면 파울."""
    return abs(spray_deg(point[0], point[1])) > FOUL_DEG


def dist_ft(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


# ---------------------------------------------------------------- 필드 그리기
def _grass_foul_outside_band(surface):
    """파울라인 바깥 잔디: 홈~외야 + 홈 아래 여백까지 한 덩어리 (최하위 레이어)."""
    ox3, ox1, oy = -4.0, 4.0, -64.0
    d_far = 142.0
    out_w = 22.0
    bot_y = -38.0 + oy

    def outside(d, foul_deg, ox, perp=out_w):
        ang = math.radians(foul_deg)
        ax, ay = math.sin(ang), math.cos(ang)
        ss = -1 if foul_deg < 0 else 1
        px, py = math.cos(ang) * ss, -math.sin(ang) * ss
        return (ax * d + px * perp + ox, ay * d + py * perp + oy)

    poly = [
        to_screen(*outside(d_far, -FOUL_DEG, ox3)),
        to_screen(*outside(0, -FOUL_DEG, ox3, 18)),
        to_screen(-62 + ox3, bot_y),
        to_screen(0, bot_y - 12),
        to_screen(62 + ox1, bot_y),
        to_screen(*outside(0, FOUL_DEG, ox1, 18)),
        to_screen(*outside(d_far, FOUL_DEG, ox1)),
        to_screen(*polar(d_far, FOUL_DEG)),
        to_screen(*HOME),
        to_screen(*polar(d_far, -FOUL_DEG)),
    ]
    pygame.draw.polygon(surface, C.GRASS, poly)


def _point_in_poly(px, py, poly):
    inside = False
    j = len(poly) - 1
    for i in range(len(poly)):
        xi, yi = poly[i]
        xj, yj = poly[j]
        if ((yi > py) != (yj > py)) and (
                px < (xj - xi) * (py - yi) / (yj - yi + 1e-9) + xi):
            inside = not inside
        j = i
    return inside


def _foul_grass_screen_poly():
    """파울 바깥 잔디 밴드(화면 좌표) — 하늘 관중 배치 시 제외."""
    ox3, ox1, oy = -4.0, 4.0, -64.0
    d_far = 142.0
    out_w = 22.0
    bot_y = -38.0 + oy

    def outside(d, foul_deg, ox, perp=out_w):
        ang = math.radians(foul_deg)
        ax, ay = math.sin(ang), math.cos(ang)
        ss = -1 if foul_deg < 0 else 1
        px, py = math.cos(ang) * ss, -math.sin(ang) * ss
        return to_screen(ax * d + px * perp + ox, ay * d + py * perp + oy)

    return [
        outside(d_far, -FOUL_DEG, ox3),
        outside(0, -FOUL_DEG, ox3, 18),
        to_screen(-62 + ox3, bot_y),
        to_screen(0, bot_y - 12),
        to_screen(62 + ox1, bot_y),
        outside(0, FOUL_DEG, ox1, 18),
        outside(d_far, FOUL_DEG, ox1),
        to_screen(*polar(d_far, FOUL_DEG)),
        to_screen(*HOME),
        to_screen(*polar(d_far, -FOUL_DEG)),
    ]


def _dark_foul_screen_poly():
    """페어존 바깥 파울 잔디(±58°) 화면 폴리곤."""
    foul_deg = 58.0
    steps = 24
    poly = [to_screen(*HOME)]
    for i in range(steps + 1):
        deg = -foul_deg + (2 * foul_deg) * i / steps
        poly.append(to_screen(*polar(fence_dist(deg), deg)))
    return poly


def _dugout_screen_poly(foul_deg, side_sign, offset_x=0.0, offset_y=0.0):
    """덕아웃 화면 좌표(관중 배치 제외용)."""
    ang = math.radians(foul_deg)
    ax, ay = math.sin(ang), math.cos(ang)
    px, py = math.cos(ang) * side_sign, -math.sin(ang) * side_sign
    d0, d1, half_w = 86.0, 142.0, 20.0

    def fpt(along, perp):
        return to_screen(ax * along + px * perp + offset_x,
                         ay * along + py * perp + offset_y)

    return [fpt(a, p) for a, p in ((d0, half_w), (d1, half_w),
                                    (d1, -half_w), (d0, -half_w))]


def _in_dugout_zone(sx, sy, poly, pad=12):
    xs = [p[0] for p in poly]
    ys = [p[1] for p in poly]
    return (min(xs) - pad <= sx <= max(xs) + pad
            and min(ys) - pad <= sy <= max(ys) + pad)


def _infield_block_poly():
    """내야 흙(홈·덕아웃 앞) — 관중 침범 방지."""
    pad, back_depth, back_half_w = 20.0, 32.0, 32.0
    return [
        to_screen(-back_half_w, -10),
        to_screen(B3[0] - pad, B3[1] + 2),
        to_screen(B2[0], B2[1] + pad),
        to_screen(B1[0] + pad, B1[1] + 2),
        to_screen(back_half_w, -10),
        to_screen(0, -back_depth),
    ]


def _infield_crowd_ok(sx, sy, grass_poly, dark_poly, dug_polys):
    """하늘 여백만 — 잔디·덕아웃·내야 흙 제외."""
    if not (8 <= sx < C.WIDTH - 8 and SB_H + 20 <= sy < C.HEIGHT - 10):
        return False
    if (_point_in_poly(sx, sy, grass_poly) or _point_in_poly(sx, sy, dark_poly)
            or _point_in_poly(sx, sy, _infield_block_poly())):
        return False
    for dug in dug_polys:
        if _in_dugout_zone(sx, sy, dug):
            return False
    return True


def _draw_infield_foul_crowd(surface):
    """±58° 직선 바깥(하늘) 여백 — 1·3루 내야 관중."""
    import random as _r

    rng = _r.Random(20260710)
    foul_wide = 58.0
    grass_poly = _foul_grass_screen_poly()
    dark_poly = _dark_foul_screen_poly()
    dug_polys = (
        _dugout_screen_poly(-FOUL_DEG, -1, -4.0, -64.0),
        _dugout_screen_poly(FOUL_DEG, 1, 4.0, -64.0),
    )

    arc_l = to_screen(*polar(fence_dist(-foul_wide), -foul_wide))
    stop_l = to_screen(*polar(108.0, -foul_wide))
    arc_r = to_screen(*polar(fence_dist(foul_wide), foul_wide))
    stop_r = to_screen(*polar(108.0, foul_wide))

    def sky_normal(ax, ay, bx, by, sky_x, sky_y):
        dx, dy = bx - ax, by - ay
        ln = math.hypot(dx, dy) or 1.0
        nx, ny = -dy / ln, dx / ln
        mx, my = (ax + bx) * 0.5, (ay + by) * 0.5
        if (sky_x - mx) * nx + (sky_y - my) * ny < 0:
            nx, ny = -nx, -ny
        return nx, ny

    mid_l_y = (arc_l[1] + stop_l[1]) * 0.5
    mid_r_y = (arc_r[1] + stop_r[1]) * 0.5
    nl_x, nl_y = sky_normal(arc_l[0], arc_l[1], stop_l[0], stop_l[1], 6, mid_l_y)
    nr_x, nr_y = sky_normal(arc_r[0], arc_r[1], stop_r[0], stop_r[1], C.WIDTH - 6, mid_r_y)

    for off, col in ((14, C.STANDS_RAIL), (28, C.STANDS_DARK)):
        pygame.draw.line(
            surface, col,
            (int(arc_l[0] + nl_x * off), int(arc_l[1] + nl_y * off)),
            (int(stop_l[0] + nl_x * off), int(stop_l[1] + nl_y * off)), 2)
        pygame.draw.line(
            surface, col,
            (int(arc_r[0] + nr_x * off), int(arc_r[1] + nr_y * off)),
            (int(stop_r[0] + nr_x * off), int(stop_r[1] + nr_y * off)), 2)

    crowd_ok = lambda sx, sy: _infield_crowd_ok(sx, sy, grass_poly, dark_poly, dug_polys)

    def _fill_sky_strip(line_a, line_b, nx, ny, u_step=6.0, off_step=7.0,
                        ext_back=70.0, ext_fwd=260.0, off_max=440.0,
                        u_phase=0.0, off_phase=0.0):
        """58° 밑줄과 같은 각도(선 방향×하늘 법선)로 하늘 여백 채우기."""
        dx = line_b[0] - line_a[0]
        dy = line_b[1] - line_a[1]
        ln = math.hypot(dx, dy) or 1.0
        ux, uy = dx / ln, dy / ln
        ext_a = (line_a[0] - ux * ext_back, line_a[1] - uy * ext_back)
        ext_b = (line_b[0] + ux * ext_fwd, line_b[1] + uy * ext_fwd)
        total = math.hypot(ext_b[0] - ext_a[0], ext_b[1] - ext_a[1])
        u = u_phase
        while u <= total:
            bx = ext_a[0] + ux * u
            by = ext_a[1] + uy * u
            off = 10.0 + off_phase
            while off <= off_max:
                sx = int(bx + nx * off)
                sy = int(by + ny * off)
                if crowd_ok(sx, sy):
                    _draw_fan_dot(surface, sx, sy, rng, radius=CROWD_DOT_R)
                off += off_step
            u += u_step

    home_l = to_screen(*polar(18.0, -foul_wide))
    home_r = to_screen(*polar(18.0, foul_wide))

    for line_a, line_b, nx, ny in (
        (arc_l, home_l, nl_x, nl_y),
        (arc_r, home_r, nr_x, nr_y),
    ):
        _fill_sky_strip(line_a, line_b, nx, ny, u_step=8.0, off_step=9.0)


def _dugout_on_foul(surface, foul_deg, side_sign, jersey_color,
                    offset_x=0.0, offset_y=0.0):
    """베이스에서 파울라인 바깥쪽으로 뻗는 덕아웃."""
    ang = math.radians(foul_deg)
    ax, ay = math.sin(ang), math.cos(ang)
    px, py = math.cos(ang) * side_sign, -math.sin(ang) * side_sign
    d0, d1, half_w = 86.0, 142.0, 20.0

    def fpt(along, perp):
        return to_screen(ax * along + px * perp + offset_x,
                         ay * along + py * perp + offset_y)

    corners = [fpt(a, p) for a, p in ((d0, half_w), (d1, half_w),
                                       (d1, -half_w), (d0, -half_w))]
    pygame.draw.polygon(surface, (46, 50, 58), corners)
    pygame.draw.polygon(surface, (30, 34, 42), corners, 2)

    bx0, by0 = fpt(d0 + 10, 4)
    bx1, by1 = fpt(d1 - 12, 4)
    pygame.draw.line(surface, (88, 92, 102), (bx0, by0), (bx1, by1), 5)
    for perp in (4, -9):
        rx0, ry0 = fpt(d0 + 10, perp)
        rx1, ry1 = fpt(d1 - 12, perp)
        for t in (0.15, 0.38, 0.62, 0.86):
            sx = int(rx0 + (rx1 - rx0) * t)
            sy = int(ry0 + (ry1 - ry0) * t)
            pygame.draw.circle(surface, jersey_color, (sx, sy + 4), 5)
            pygame.draw.circle(surface, (235, 205, 168), (sx, sy), 4)


def _draw_dugouts(surface):
    """3루·1루 베이스에서 파울라인 바깥 덕아웃."""
    # 3루: 오른쪽·아래 / 1루: 왼쪽·아래 (기존 -84/+84 에서 대각 이동)
    _dugout_on_foul(surface, -FOUL_DEG, -1, C.TEAM_COLORS[0],
                    offset_x=-4.0, offset_y=-64.0)
    _dugout_on_foul(surface, FOUL_DEG, 1, C.TEAM_COLORS[1],
                    offset_x=4.0, offset_y=-64.0)


def _draw_foul_pole(surface, foul_deg):
    """파울 폴: 파울라인과 외야 담장이 만나는 코너(탑다운)."""
    dist = fence_dist(foul_deg)
    bx, by = to_screen(*polar(dist, foul_deg))
    r = max(6, int(8 * SCALE / 12))

    pygame.draw.circle(surface, (150, 100, 18), (bx, by), r + 2)
    pygame.draw.circle(surface, C.FENCE_TOP, (bx, by), r)
    pygame.draw.circle(surface, (255, 248, 210), (bx, by), max(2, r // 3))

    tip = to_screen(*polar(dist + 16, foul_deg))
    w = max(3, r // 2 + 1)
    pygame.draw.line(surface, C.FENCE_TOP, (bx, by), tip, w)
    pygame.draw.line(surface, (150, 100, 18), (bx, by), tip, 1)


def draw_field(surface):
    steps = 40
    surface.blit(_crowd_surface(), (0, 0))

    # 파울 잔디 (페어존 바깥, 파울라인 쪽으로 조금 더 넓게)
    foul_deg = 58.0
    foul = [to_screen(*HOME)]
    for i in range(steps + 1):
        deg = -foul_deg + (2 * foul_deg) * i / steps
        foul.append(to_screen(*polar(fence_dist(deg), deg)))
    pygame.draw.polygon(surface, C.GRASS_DARK, foul)

    # 페어 잔디
    fair = [to_screen(*HOME)]
    for i in range(steps + 1):
        deg = -FOUL_DEG + (2 * FOUL_DEG) * i / steps
        fair.append(to_screen(*polar(fence_dist(deg), deg)))
    pygame.draw.polygon(surface, C.GRASS, fair)

    # 파울라인 바깥 잔디(홈~외야, 홈 아래 하늘색 여백 제거) — 최하위 레이어
    _grass_foul_outside_band(surface)

    # 잔디 줄무늬(부채꼴 링 — 이전 야구장 형태)
    for ring in range(1, 8):
        if ring % 2 == 0:
            continue
        r0, r1 = ring / 8.0, (ring + 1) / 8.0
        poly = []
        for i in range(steps + 1):
            deg = -FOUL_DEG + (2 * FOUL_DEG) * i / steps
            poly.append(to_screen(*polar(fence_dist(deg) * r1, deg)))
        for i in range(steps + 1):
            deg = FOUL_DEG - (2 * FOUL_DEG) * i / steps
            poly.append(to_screen(*polar(fence_dist(deg) * r0, deg)))
        pygame.draw.polygon(surface, C.GRASS_LIGHT, poly)

    # 워닝트랙
    track_in, track_out = [], []
    for i in range(steps + 1):
        deg = -FOUL_DEG + (2 * FOUL_DEG) * i / steps
        track_in.append(to_screen(*polar(fence_dist(deg) * 0.91, deg)))
        track_out.append(to_screen(*polar(fence_dist(deg) * 0.97, deg)))
    pygame.draw.polygon(surface, C.DIRT_DARK, track_in + list(reversed(track_out)))

    # 외야 담장(낮은 초록 벽 + 노란 라인)
    wall_in, wall_out = [], []
    for i in range(steps + 1):
        deg = -FOUL_DEG + (2 * FOUL_DEG) * i / steps
        wall_in.append(to_screen(*polar(fence_dist(deg) * 0.99, deg)))
        wall_out.append(to_screen(*polar(fence_dist(deg) * 1.025, deg)))
    pygame.draw.polygon(surface, C.WALL, wall_in + list(reversed(wall_out)))
    wall_top = []
    for i in range(steps + 1):
        deg = -FOUL_DEG + (2 * FOUL_DEG) * i / steps
        wall_top.append(to_screen(*polar(fence_dist(deg) * 1.025, deg)))
    pygame.draw.lines(surface, C.WALL_TOP, False, wall_top, 3)

    # 중견 전광판 + 야간 조명탑
    _draw_center_scoreboard(surface)
    board_y = FIELD_TOP + 22
    _draw_light_tower(surface, CX - 168, board_y + 14)
    _draw_light_tower(surface, CX + 168, board_y + 14)

    # 내야 흙 (홈 뒤 심판·포수 구역 포함)
    pad = 20.0
    back_depth = 32.0
    back_half_w = 32.0
    inf = [to_screen(-back_half_w, -10),
           to_screen(B3[0] - pad, B3[1] + 2),
           to_screen(B2[0], B2[1] + pad),
           to_screen(B1[0] + pad, B1[1] + 2),
           to_screen(back_half_w, -10),
           to_screen(0, -back_depth)]
    pygame.draw.polygon(surface, C.INFIELD, inf)
    pygame.draw.polygon(surface, C.INFIELD_DARK, inf, 2)

    # 내야 잔디
    g = 26.0
    infg = [to_screen(HOME[0], HOME[1] + g),
            to_screen(B1[0] - g * 0.3, B1[1] - 2),
            to_screen(B2[0], B2[1] - g),
            to_screen(B3[0] + g * 0.3, B3[1] - 2)]
    pygame.draw.polygon(surface, C.GRASS_LIGHT, infg)

    # 마운드
    mx, my = to_screen(*MOUND)
    mr = max(13, int(18 * SCALE))
    pygame.draw.circle(surface, C.MOUND_DIRT, (mx, my), mr)
    pygame.draw.circle(surface, C.INFIELD_DARK, (mx, my), mr, 2)
    pygame.draw.circle(surface, C.WHITE, (mx, my), max(3, mr // 5))

    # 파울 라인
    pygame.draw.line(surface, C.LINE, to_screen(*HOME),
                     to_screen(*polar(fence_dist(-FOUL_DEG), -FOUL_DEG)), 2)
    pygame.draw.line(surface, C.LINE, to_screen(*HOME),
                     to_screen(*polar(fence_dist(FOUL_DEG), FOUL_DEG)), 2)
    _draw_foul_pole(surface, -FOUL_DEG)
    _draw_foul_pole(surface, FOUL_DEG)

    # 베이스
    for key in ("1B", "2B", "3B"):
        _draw_base(surface, BASES_XY[key])
    _draw_home_plate(surface)
    _draw_dugouts(surface)
    _draw_infield_foul_crowd(surface)


def _draw_base(surface, ft):
    x, y = to_screen(*ft)
    s = 7
    pts = [(x, y - s), (x + s, y), (x, y + s), (x - s, y)]
    pygame.draw.polygon(surface, C.WHITE, pts)
    pygame.draw.polygon(surface, (150, 150, 150), pts, 1)


def _draw_home_plate(surface):
    x, y = to_screen(*HOME)
    pygame.draw.polygon(surface, C.WHITE,
                        [(x - 7, y - 6), (x + 7, y - 6), (x + 7, y),
                         (x, y + 7), (x - 7, y)])


# ---------------------------------------------------------------- 캐릭터
def draw_fielder(surface, ft, cap_color=C.TEAM_AWAY, glove_side=1, name=""):
    """귀여운 탑다운 수비수: 몸(유니폼)+모자+글러브."""
    x, y = to_screen(*ft)
    # 그림자
    pygame.draw.ellipse(surface, (30, 70, 34), (x - 9, y + 5, 18, 7))
    # 몸
    pygame.draw.circle(surface, C.JERSEY, (x, y), 9)
    # 글러브
    pygame.draw.circle(surface, C.CAP_GLOVE, (x + glove_side * 10, y + 1), 4)
    # 모자
    pygame.draw.circle(surface, cap_color, (x, y - 1), 6)
    pygame.draw.ellipse(surface, cap_color, (x - 3, y - 8, 6, 4))  # 챙


def draw_catcher(surface, cap_color=C.TEAM_AWAY):
    x, y = to_screen(*CATCHER)
    pygame.draw.ellipse(surface, (30, 70, 34), (x - 10, y + 5, 20, 7))
    pygame.draw.circle(surface, (40, 44, 54), (x, y), 10)      # 보호장비
    pygame.draw.circle(surface, cap_color, (x, y), 6)
    pygame.draw.circle(surface, C.CAP_GLOVE, (x, y + 8), 5)     # 미트


def draw_umpire(surface):
    x, y = to_screen(*UMPIRE)
    pygame.draw.ellipse(surface, (30, 70, 34), (x - 9, y + 4, 18, 6))
    pygame.draw.circle(surface, C.UMP_COLOR, (x, y), 9)
    pygame.draw.circle(surface, (90, 94, 104), (x, y - 1), 5)   # 헬멧


def _smoothstep(t):
    t = max(0.0, min(1.0, t))
    return t * t * (3 - 2 * t)


def draw_menu_batter(surface, anim_t):
    """타이틀용 좌·우 실루엣."""
    ground = 212
    bob = math.sin(anim_t * 2.2) * 2.5

    def blit_sprite(img, cx):
        x = cx - img.get_width() // 2
        y = int(ground - img.get_height() + bob)
        shadow_w = int(img.get_width() * 0.72)
        shadow_x = cx - shadow_w // 2
        pygame.draw.ellipse(surface, (22, 52, 30),
                            (shadow_x, ground - 6, shadow_w, 12))
        surface.blit(img, (x, y))

    blit_sprite(get_menu_scene(), 178)
    blit_sprite(get_menu_batter(), 738)


def draw_batter_boxes(surface):
    """홈플레이트 좌우 타석 박스."""
    hx, hy = to_screen(*HOME)
    bw, bh = 22, 34
    gap = 12
    for sign in (-1, 1):
        rect = pygame.Rect(0, 0, bw, bh)
        if sign < 0:
            rect.topright = (hx - gap, hy - bh // 2)
        else:
            rect.topleft = (hx + gap, hy - bh // 2)
        pygame.draw.rect(surface, (236, 236, 236), rect, width=2)


def draw_batter(surface, right_handed=True, swing=0.0, jersey_color=None):
    """올바른 타석 박스 안에 선 타자: 헬멧 + 방망이(스윙 회전).

    우타 = 3루쪽(좌측 박스), 좌타 = 1루쪽(우측 박스).
    """
    if jersey_color is None:
        jersey_color = C.TEAM_HOME
    draw_batter_boxes(surface)
    hx, hy = to_screen(*HOME)
    box_sign = -1 if right_handed else 1        # 화면상 서는 쪽
    x = hx + box_sign * 23
    y = hy - 4

    # 그림자/몸/헬멧
    pygame.draw.ellipse(surface, (30, 70, 34), (x - 9, y + 6, 18, 7))
    pygame.draw.circle(surface, jersey_color, (x, y), 10)
    pygame.draw.circle(surface, (34, 40, 96), (x, y - 1), 6)

    # 방망이: 홈플레이트 위를 향해 회전. mirror 로 스윙 방향 반전
    mirror = 1 if right_handed else -1
    pivot = (x, y)
    bat_len = 30
    start_ang = 46.0
    end_ang = 210.0
    ang = math.radians(start_ang + (end_ang - start_ang) * _smoothstep(swing))
    tip = (pivot[0] - box_sign * bat_len * math.cos(ang),
           pivot[1] - bat_len * math.sin(ang))
    if 0.04 < swing < 0.98:
        for k in range(1, 4):
            pa = math.radians(start_ang + (end_ang - start_ang) *
                              _smoothstep(max(0.0, swing - k * 0.12)))
            pt = (pivot[0] - box_sign * bat_len * math.cos(pa),
                  pivot[1] - bat_len * math.sin(pa))
            pygame.draw.line(surface, (235, 235, 235), pivot, pt, max(1, 4 - k))
    pygame.draw.line(surface, (150, 96, 48), pivot, tip, 5)
    pygame.draw.circle(surface, (210, 200, 190), (int(tip[0]), int(tip[1])), 3)


def draw_ball(surface, ft, height=0.0):
    """공. height(피트)만큼 위로 띄우고 그림자를 남긴다."""
    x, y = to_screen(*ft)
    hpx = int(height * SCALE * 0.6)
    # 그림자
    pygame.draw.circle(surface, (40, 90, 44), (x, y), 4)
    bx, by = x, y - hpx
    r = 5 + int(height / 30)
    pygame.draw.circle(surface, C.WHITE, (bx, by), r)
    pygame.draw.circle(surface, C.ACCENT, (bx, by), r, 1)


def draw_runner(surface, ft, color=C.TEAM_HOME):
    x, y = to_screen(*ft)
    pygame.draw.circle(surface, color, (x, y), 8)
    pygame.draw.circle(surface, C.WHITE, (x, y), 8, 2)
