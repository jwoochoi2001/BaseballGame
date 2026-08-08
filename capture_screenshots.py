"""게임 화면 스크린샷 자동 캡처 (README용).

실행: python capture_screenshots.py
"""
from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame

from baseball import config as C
from baseball.app import (
    AboutScene,
    GameOverScene,
    HelpScene,
    LineupScene,
    MenuScene,
    P_INNING_CHANGE,
    P_PITCH,
    P_RESULT,
    P_ROUND_CLEAR,
    P_SELECT,
    PlayScene,
)
from baseball.gamestate import LiveGame

OUT_DIR = Path(__file__).resolve().parent / "images"


class _StubApp:
    def change_scene(self, scene):
        pass


def _save(scene, filename: str) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    pygame.init()
    screen = pygame.display.set_mode((C.WIDTH, C.HEIGHT))
    scene.draw(screen)
    pygame.display.flip()
    path = OUT_DIR / filename
    pygame.image.save(screen, str(path))
    print(f"saved {path}")


def _lineups():
    names = list(C.DEFAULT_LINEUP)
    return [names, names]


def _make_2p_game() -> LiveGame:
    game = LiveGame(False, _lineups(), [C.DEFAULT_TEAM_AWAY, C.DEFAULT_TEAM_HOME])
    game.right = [list(C.DEFAULT_RIGHT), list(C.DEFAULT_RIGHT)]
    return game


def _fill_lines(game: LiveGame, away: list[int], home: list[int]):
    game.line = [list(away), list(home)]
    while len(game.line[0]) < 9:
        game.line[0].append(0)
    while len(game.line[1]) < 9:
        game.line[1].append(0)


def _play_scene(game: LiveGame) -> PlayScene:
    return PlayScene(_StubApp(), game)


def capture_all():
    app = _StubApp()

    _save(MenuScene(app), "01_menu.png")
    _save(HelpScene(app), "02_help.png")
    _save(AboutScene(app, None), "03_about.png")
    _save(LineupScene(app, one_player=True), "04_lineup_1p.png")
    _save(LineupScene(app, one_player=False), "05_lineup_2p.png")

    # 2인 — 구종 선택
    g = _make_2p_game()
    g.inning = 3
    g.half = "top"
    g.batting_team = 0
    g.outs = 1
    g.bases = [True, False, False]
    g.score = [2, 1]
    _fill_lines(g, [1, 1, 0, 0, 0, 0, 0, 0, 0], [0, 1, 0, 0, 0, 0, 0, 0, 0])
    s = _play_scene(g)
    s.phase = P_SELECT
    s.strikes = 1
    s.balls = 2
    s.pitch_name = "슬라이더"
    s.pitch_speed = 128
    _save(s, "06_play_2p_select.png")

    # 2인 — 투수교체 창
    s._open_pitcher_sub()
    _save(s, "06b_pitcher_sub.png")

    # 2인 — 타격(만루 + 게이지)
    g = _make_2p_game()
    g.inning = 7
    g.half = "bottom"
    g.batting_team = 1
    g.outs = 2
    g.bases = [True, True, True]
    g.score = [3, 4]
    _fill_lines(g, [1, 0, 1, 0, 0, 1, 0, 0, 0], [0, 1, 0, 2, 0, 1, 0, 0, 0])
    g.batter_stats[1][3] = {"ab": 2, "h": 1, "hr": 0, "rbi": 2, "bb": 1, "k": 0}
    s = _play_scene(g)
    s.phase = P_PITCH
    s.strikes = 1
    s.balls = 3
    s.t = 0.66
    s.pitch_name = "패스트볼"
    s.pitch_speed = 149
    _save(s, "07_play_2p_pitch.png")

    # 2인 — 일시정지
    s.paused = True
    _save(s, "08_play_2p_pause.png")

    # 2인 — 홈런 결과
    s = _play_scene(_make_2p_game())
    s.phase = P_RESULT
    s.result_text = "GRAND SLAM!\n만루 홈런!\n+4점"
    s.result_color = C.GOOD
    _save(s, "09_result_homerun.png")

    # 2인 — 밀어내기
    s = _play_scene(_make_2p_game())
    s.phase = P_RESULT
    s.result_text = "밀어내기\n+1점"
    s.result_color = C.GOOD
    g2 = s.game
    g2.bases = [True, True, True]
    g2.score = [2, 3]
    _save(s, "10_result_push_walk.png")

    # 2인 — 삼진
    s = _play_scene(_make_2p_game())
    s.phase = P_RESULT
    s.result_text = "삼진 아웃!"
    s.result_color = C.ACCENT
    _save(s, "11_result_strikeout.png")

    # 2인 — 이닝교대
    g = _make_2p_game()
    g.inning = 4
    g.half = "bottom"
    g.batting_team = 1
    s = _play_scene(g)
    s.phase = P_INNING_CHANGE
    _save(s, "12_inning_change.png")

    # 1인 — 플레이
    g1 = LiveGame(True, [list(C.DEFAULT_LINEUP), [C.DEFAULT_1P_BATTER]],
                  ["상대팀", "우리팀"])
    g1.solo_points = 420
    g1.solo_round = 2
    g1.solo_outs_used = 4
    g1.bases = [True, False, False]
    s = _play_scene(g1)
    s.phase = P_PITCH
    s.t = 0.70
    s.pitch_name = "커브"
    s.pitch_speed = 118
    _save(s, "13_play_1p.png")

    # 1인 — 라운드 클리어
    s.phase = P_ROUND_CLEAR
    _save(s, "14_round_clear.png")

    # 1인 — 일시정지
    s.phase = P_PITCH
    s.paused = True
    _save(s, "15_pause_1p.png")

    # 1인 — 게임 오버
    g1.solo_points = 580
    g1.solo_round = 3
    g1.solo_outs_used = g1.solo_outs_limit()
    g1.solo_game_over = True
    g1.hits = [0, 14]
    _save(GameOverScene(app, g1), "16_gameover_1p.png")

    # 2인 — 원정 승리
    g = _make_2p_game()
    g.score = [6, 3]
    g.hits = [9, 6]
    g.errors = [0, 1]
    g.walks = [3, 2]
    _fill_lines(g, [2, 1, 0, 1, 1, 1, 0, 0, 0], [1, 0, 1, 0, 0, 1, 0, 0, 0])
    g.batter_stats[0][1] = {"ab": 4, "h": 3, "hr": 1, "rbi": 4, "bb": 1, "k": 0}
    over_scene = GameOverScene(app, g)
    _save(over_scene, "17_gameover_win_away.png")

    # 2인 — 기록(타자 기록표)
    over_scene.show_stats = True
    _save(over_scene, "17b_boxscore.png")

    # 2인 — 홈 승리
    g = _make_2p_game()
    g.score = [2, 5]
    g.hits = [5, 10]
    g.errors = [2, 0]
    g.walks = [1, 4]
    _fill_lines(g, [1, 0, 0, 1, 0, 0, 0, 0, 0], [0, 2, 1, 0, 1, 1, 0, 0, 0])
    g.batter_stats[1][4] = {"ab": 4, "h": 3, "hr": 0, "rbi": 3, "bb": 1, "k": 0}
    _save(GameOverScene(app, g), "18_gameover_win_home.png")

    # 2인 — 끝내기 승리
    g = _make_2p_game()
    g.inning = 9
    g.half = "bottom"
    g.score = [4, 5]
    g.walk_off = True
    g.hits = [7, 8]
    g.walks = [2, 3]
    _fill_lines(g, [1, 0, 1, 0, 1, 0, 1, 0, 0], [0, 1, 0, 1, 0, 1, 0, 0, 1])
    g.batter_stats[1][2] = {"ab": 3, "h": 2, "hr": 0, "rbi": 2, "bb": 2, "k": 1}
    _save(GameOverScene(app, g), "19_gameover_walkoff.png")

    # 2인 — 무승부
    g = _make_2p_game()
    g.inning = 9
    g.score = [4, 4]
    g.game_tied = True
    g.hits = [6, 6]
    g.errors = [1, 1]
    g.walks = [2, 2]
    _fill_lines(g, [1, 0, 1, 0, 1, 0, 1, 0, 0], [0, 1, 0, 1, 0, 1, 0, 1, 0])
    _save(GameOverScene(app, g), "20_gameover_tie.png")

    pygame.quit()


if __name__ == "__main__":
    capture_all()
