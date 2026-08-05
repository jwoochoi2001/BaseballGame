"""경기 진행 상태(라인스코어/아웃/주자/득점)와 탑다운 타구 판정."""
import math
import random

from . import config as C
from . import field as F


def solo_target_for_round(round_num):
    """라운드별 누적 목표 점수(구간마다 필요 점수가 점점 증가)."""
    if round_num <= 1:
        return C.SOLO_ROUND_BASE
    target = C.SOLO_ROUND_BASE
    for i in range(round_num - 1):
        target += C.SOLO_ROUND_GAP_START + C.SOLO_ROUND_GAP_STEP * i
    return target


class LiveGame:
    def __init__(self, one_player, lineups, team_names):
        self.one_player = one_player
        self.lineups = lineups
        self.team_names = team_names
        self.innings = C.INNINGS

        self.inning = 1
        self.half = "top"          # top=원정(팀0) / bottom=홈(팀1)
        self.batting_team = 0
        self.outs = 0
        self.bases = [False, False, False]
        self.score = [0, 0]
        self.hits = [0, 0]
        self.errors = [0, 0]
        self.walks = [0, 0]
        self.batter_idx = [0, 0]
        self.line = [[], []]       # 이닝별 득점
        self.last_runs = 0
        self.pending_inning_change = False
        self.walk_off = False
        self.skipped_bottom_9th = False
        self.game_tied = False
        # 경기가 끝난 순간의 이닝 표시를 그대로 고정(9회 이후로 넘어가
        # "10회 초" 처럼 보이지 않도록)
        self._final_half_label = None
        # 팀별 좌우타 정보
        self.right = [list(C.DEFAULT_RIGHT), list(C.DEFAULT_RIGHT)]
        # 팀별 선발투수 이름·투구 손(표시용, 실제 투구 로직에는 영향 없음)
        self.pitchers = ["", ""]
        self.pitcher_right = [True, True]

        if one_player:
            self.batting_team = 1
            self.half = "bottom"
            self.solo_points = 0
            self.solo_round = 1
            self.solo_round_start_points = 0
            self.solo_outs_used = 0
            self.solo_last_gain = 0
            self.solo_game_over = False
            self.solo_round_clear_pending = False
        else:
            self.batter_stats = [
                [{"ab": 0, "h": 0, "hr": 0, "rbi": 0, "bb": 0} for _ in range(9)]
                for _ in range(2)
            ]

        self._begin_half()

    # ----------------------------------------------------------- 조회
    @property
    def defending_team(self):
        return 1 - self.batting_team

    def current_batter_name(self):
        idx = self.batter_idx[self.batting_team]
        lineup = self.lineups[self.batting_team]
        return lineup[idx % len(lineup)], (idx % len(lineup)) + 1

    def batter_is_right(self):
        idx = self.batter_idx[self.batting_team]
        r = self.right[self.batting_team]
        return r[idx % len(r)]

    def runners_on(self):
        return sum(self.bases)

    def is_over(self):
        """9회 종료 또는 1인 모드 탈락."""
        if self.one_player:
            return self.solo_game_over
        return self.inning > self.innings

    @property
    def outs_for_rules(self):
        """병살·태그업 등 이닝 내 아웃 규칙용(1인은 3아웃 단위로 순환)."""
        if self.one_player:
            return self.solo_outs_used % C.OUTS_PER_INNING
        return self.outs

    def solo_target(self):
        """현재 라운드 누적 목표 점수."""
        return solo_target_for_round(self.solo_round)

    def solo_prev_target(self):
        """이전 라운드까지의 누적 목표."""
        return solo_target_for_round(self.solo_round - 1) if self.solo_round > 1 else 0

    @property
    def solo_rounds_cleared(self):
        """클리어한 라운드 수(탈락 시 현재 라운드 미포함)."""
        return max(0, self.solo_round - 1)

    def solo_outs_limit(self):
        """현재 라운드 허용 아웃 수(라운드가 올라갈수록 감소)."""
        dec = (self.solo_round - 1) * C.SOLO_OUTS_STEP
        return max(C.SOLO_OUTS_MIN, C.SOLO_OUTS_START - dec)

    def solo_outs_left(self):
        return max(0, self.solo_outs_limit() - self.solo_outs_used)

    def _solo_hit_points(self, plan, runs):
        kind = plan["kind"]
        bases = plan.get("bases", 0)
        if kind == "hr":
            pts = C.SOLO_HIT_POINTS[4]
        elif kind in ("hit", "error"):
            pts = C.SOLO_HIT_POINTS.get(bases, C.SOLO_HIT_POINTS[1])
        else:
            pts = 0
        return pts + runs * C.SOLO_RUN_POINTS

    def _solo_award_points(self, pts):
        self.solo_last_gain = pts
        if pts > 0:
            self.solo_points += pts
        while self.solo_points >= self.solo_target():
            self._solo_advance_round()

    def _solo_advance_round(self):
        self.solo_round += 1
        self.solo_outs_used = 0
        self.solo_round_start_points = self.solo_points
        self.solo_round_clear_pending = True
        self.bases = [False, False, False]

    def _solo_consume_outs(self, n=1):
        if n <= 0:
            return
        self.solo_outs_used += n
        if (self.solo_outs_used >= self.solo_outs_limit()
                and self.solo_points < self.solo_target()):
            self.solo_game_over = True

    def half_label(self):
        if self._final_half_label is not None:
            return self._final_half_label
        return f"{self.inning}회 {'초' if self.half == 'top' else '말'}"

    def format_batter_stats_compact(self, team_idx, slot):
        """타수·안타·타점·홈런·볼넷 (볼넷은 타수 미포함)."""
        st = self.batter_stats[team_idx][slot]
        return (f"{st['ab']}타수 {st['h']}안타 {st['rbi']}타점 "
                f"{st['hr']}홈런 {st['bb']}볼넷")

    def format_batter_stat(self, team_idx, slot, name=None):
        """팀·타순별 타격 기록 문자열 (MVP 등)."""
        if name is None:
            name = self.lineups[team_idx][slot]
        return f"{slot + 1}번 {name}  {self.format_batter_stats_compact(team_idx, slot)}"

    def current_batter_stats_compact(self):
        """현재 타석 타자의 팀별 기록(숫자만)."""
        t = self.batting_team
        slot = self.batter_idx[t] % len(self.lineups[t])
        return self.format_batter_stats_compact(t, slot)

    def winning_team(self):
        if self.one_player or self.score[0] == self.score[1]:
            return None
        return 0 if self.score[0] > self.score[1] else 1

    def pick_mvp(self):
        """승리팀 MVP. 무승부면 None."""
        wt = self.winning_team()
        if wt is None:
            return None
        best_slot = None
        best_key = (-1, -1, -1, -1)
        for i, st in enumerate(self.batter_stats[wt]):
            if st["ab"] == 0:
                continue
            key = (st["rbi"], st["hr"], st["h"], st["ab"])
            if key > best_key:
                best_key = key
                best_slot = i
        if best_slot is None or best_key == (0, 0, 0, 0):
            return None
        name = self.lineups[wt][best_slot]
        return dict(team=wt, slot=best_slot, name=name,
                    stats=self.batter_stats[wt][best_slot],
                    line=self.format_batter_stat(wt, best_slot, name))

    def _record_plate_appearance(self, *, walk=False, hit=False, hr=False, runs=0):
        """팀별 타자 기록(동일 이름이라도 팀마다 분리)."""
        if self.one_player:
            return
        t = self.batting_team
        slot = self.batter_idx[t] % len(self.lineups[t])
        st = self.batter_stats[t][slot]
        if walk:
            st["bb"] += 1
            return
        st["ab"] += 1
        if hit:
            st["h"] += 1
        if hr:
            st["hr"] += 1
        st["rbi"] += runs

    # ----------------------------------------------------------- 이닝 진행
    def _begin_half(self):
        t = self.batting_team
        while len(self.line[t]) < self.inning:
            self.line[t].append(0)

    def _end_half(self):
        pre_label = self.half_label()
        self.outs = 0
        self.bases = [False, False, False]
        if self.half == "top":
            # 9회초 3아웃: 홈팀이 이기면 9회말 없이 경기 종료
            if (self.inning == self.innings
                    and self.score[1] > self.score[0]):
                self.skipped_bottom_9th = True
                self.inning = self.innings + 1
                self._final_half_label = pre_label
                return
            self.half = "bottom"
            self.batting_team = 1
        else:
            if (self.inning == self.innings
                    and self.score[0] == self.score[1]):
                self.game_tied = True
            self.half = "top"
            self.batting_team = 0
            self.inning += 1
        if self.is_over():
            self._final_half_label = pre_label
        else:
            self.pending_inning_change = True
            self._begin_half()

    def next_batter(self):
        self.batter_idx[self.batting_team] += 1

    def _add_runs(self, r):
        if r <= 0:
            return
        t = self.batting_team
        while len(self.line[t]) < self.inning:
            self.line[t].append(0)
        self.line[t][self.inning - 1] += r
        self.score[t] += r

    def _add_out(self):
        self.outs += 1
        if self.outs >= C.OUTS_PER_INNING:
            self._end_half()

    def _maybe_walk_off(self, score_before=None):
        """9회말 홈팀이 1점이라도 앞서면 끝내기(홈팀 승리). 연장 없음."""
        if (self.inning == self.innings and self.half == "bottom"
                and self.batting_team == 1 and self.score[1] > self.score[0]):
            self._final_half_label = self.half_label()
            self.walk_off = True
            self.inning = self.innings + 1
            return True
        return False

    def _advance(self, n):
        """주자를 n루씩 진루시키고 득점 수를 돌려준다."""
        positions = [i + 1 for i, on in enumerate(self.bases) if on]
        runs = 0
        newp = []
        for p in positions:
            np = p + n
            if np >= 4:
                runs += 1
            else:
                newp.append(np)
        if n >= 4:
            runs += 1
        else:
            newp.append(n)
        self.bases = [(i + 1) in newp for i in range(3)]
        return runs

    # ----------------------------------------------------------- 결과 반영
    def strikeout(self):
        self._record_plate_appearance()
        self.next_batter()
        if self.one_player:
            self.solo_last_gain = 0
            self._solo_consume_outs(1)
        else:
            self._add_out()

    def walk(self):
        """4구 볼넷: 타자 1루 진루(주자는 포스 상황만 진루)."""
        if not self.one_player:
            self.walks[self.batting_team] += 1
        else:
            self.walks[1] += 1
        runs = self._walk_advance()
        score_before = tuple(self.score)
        if self.one_player:
            self._solo_award_points(runs * C.SOLO_RUN_POINTS)
        elif runs:
            self._add_runs(runs)
        self._record_plate_appearance(walk=True)
        self.next_batter()
        self.last_runs = runs
        if not self.one_player:
            self._maybe_walk_off(score_before)
        return runs

    def _walk_advance(self):
        """볼넷: 포스 진루만. 만루 볼넷은 1점 + 만루 유지."""
        b0, b1, b2 = self.bases
        if b0 and b1 and b2:
            self.bases = [True, True, True]
            return 1
        if b0 and b1:
            self.bases = [True, True, True]
            return 0
        if b0:
            self.bases = [True, True, b2]
            return 0
        self.bases = [True, b1, b2]
        return 0

    def apply_plan(self, plan):
        kind = plan["kind"]
        runs = 0
        if kind in ("hit", "hr", "error"):
            runs = self._advance(plan["bases"])
            if self.one_player:
                if kind != "error":
                    self.hits[1] += 1
                self._solo_award_points(self._solo_hit_points(plan, runs))
            else:
                if kind == "error":
                    self.errors[self.defending_team] += 1
                else:
                    self.hits[self.batting_team] += 1
                score_before = tuple(self.score)
                self._add_runs(runs)
                self._maybe_walk_off(score_before)
            self._record_plate_appearance(
                hit=(kind in ("hit", "hr")), hr=(kind == "hr"), runs=runs)
            self.next_batter()
        elif kind == "out":
            rules_outs = self.outs_for_rules
            outs_to_add = plan.get("outs", 1)
            ends_inning = rules_outs + outs_to_add >= C.OUTS_PER_INNING
            score_before = tuple(self.score)
            pre = plan.get("bases_at_pitch", list(self.bases))
            if plan.get("tag_up") and rules_outs < C.OUTS_PER_INNING - 1:
                if self.bases[2]:
                    self.bases[2] = False
                    runs += 1
                if self.bases[1]:
                    self.bases[1] = False
                    self.bases[2] = True
            elif plan.get("double_play"):
                self.bases, dp_runs = _apply_double_play_bases(list(pre))
                if pre[2] and dp_runs < 1:
                    dp_runs = 1
                    self.bases = [False, False, pre[1]]
                if dp_runs:
                    runs += dp_runs
            elif plan.get("force_out_2nd"):
                self.bases, fc_runs = _apply_fc_second_bases(list(pre))
                if fc_runs:
                    runs += fc_runs
            elif plan.get("out_at_first"):
                self.bases, adv_runs = _apply_ground_out_first(list(pre))
                if adv_runs:
                    runs += adv_runs
            # 3아웃으로 이닝이 끝나는 플레이에서는 득점 무효
            if ends_inning:
                runs = 0
            if runs and not self.one_player:
                self._add_runs(runs)
            self._record_plate_appearance(runs=runs)
            self.next_batter()
            if self.one_player:
                self._solo_award_points(runs * C.SOLO_RUN_POINTS)
                self._solo_consume_outs(outs_to_add)
            else:
                for _ in range(outs_to_add):
                    if self.outs < C.OUTS_PER_INNING and not self.is_over():
                        self._add_out()
                if runs:
                    self._maybe_walk_off(score_before)
        self.last_runs = runs
        return runs


# ================================================================ 타구 판정
RUN_HOME_TO_FIRST = 4.1     # 타자주자 1루 도달 시간(초)
THROW_SPEED = 115.0          # 송구 속도(ft/s)
FIELDER_SPEED = 27.0         # 수비 이동 속도(ft/s)
RELEASE = 0.55               # 포구 후 송구까지 지연
CATCH_TIME_CAP = 2.55        # 낙구 지점까지 달릴 수 있는 시간 상한
PITCHER_GROUND_REACH_FT = 6.0  # 투수 땅볼 수비 폭(정면 강습타만, 좌우로 넓게 못 감)

INFIELDERS = ("투수", "1루수", "2루수", "유격수", "3루수")
INFIELDER_SET = frozenset(INFIELDERS)


def _foul_plan(landing):
    return dict(kind="foul", label="파울", ball_type="foul",
                landing=landing, field_by=None, throw_to=None,
                bases=0, outs=0, double_play=False, sac_fly=False, error=False)


def _double_play_details(fielder):
    """병살 연출용: 표기 코드, 2루 커버 수비수."""
    if fielder == "유격수":
        return "6-4-3", "2루수"
    if fielder == "2루수":
        return "4-6-3", "유격수"
    if fielder == "3루수":
        return "5-4-3", "2루수"
    if fielder == "1루수":
        return "3-6-3", "유격수"
    return "병살", "2루수"


def _fc_second_cover(fielder):
    """1루 주자 포스 아웃(2루 송구) 시 2루 커버 수비수."""
    if fielder == "2루수":
        return "유격수"
    if fielder == "유격수":
        return "2루수"
    return "2루수"


def _apply_double_play_bases(bases):
    """병살: 1루·타자 아웃, 2루→3루, 3루 주자는 홈인."""
    b0, b1, b2 = bases
    runs = 1 if b2 else 0
    return [False, False, b1], runs


def _apply_fc_second_bases(bases):
    """2루 포스 아웃: 1루 주자 아웃, 타자 1루, 2루→3루. 3루 주자는 홈인."""
    b0, b1, b2 = bases
    runs = 1 if b2 else 0
    return [True, False, b1], runs


def _apply_ground_out_first(bases):
    """1루 송구 아웃: 타자 아웃, 주자 1루씩 진루. 3루 주자는 홈인."""
    b0, b1, b2 = bases
    runs = 1 if b2 else 0
    if not b0:
        return [False, False, b1], runs
    return [False, b0, b1], runs


def _hr_presentation(bases):
    """홈런 연출 문구 (영문 타이틀 + 한글 부제)."""
    r = sum(bases)
    if r >= 3:
        return "GRAND SLAM!", "만루 홈런!"
    if r == 2:
        return "THREE-RUN HOMER!", "쓰리런 홈런!"
    if r == 1:
        return "TWO-RUN HOMER!", "투런 홈런!"
    return "HOME RUN!", "솔로 홈런!"


def _nearest_catcher(point, time_budget, radius=7.0, candidates=None):
    """time_budget 안에 point 에 닿을 수 있는 수비수와, 잡을 수 있는지.

    time_budget 은 CATCH_TIME_CAP 로 제한해 외야 사이(갭)를 뚫는 안타가 나오게 한다.
    """
    cand = candidates or F.FIELDERS_HOME
    tb = min(time_budget, CATCH_TIME_CAP)
    best, bestgap, caught = None, 1e9, False
    for name, pos in cand.items():
        d = F.dist_ft(pos, point)
        reach = FIELDER_SPEED * tb + radius
        gap = d - reach
        if gap < bestgap:
            bestgap, best = gap, name
        if d <= reach:
            caught = True
    return best, caught


def resolve_batted_ball(power, spray_deg, launch_deg, bases, outs):
    """타구 물리/수비 판정.

    power 0~1, spray_deg(-=좌/+=우), launch_deg(0=땅볼~높을수록 뜬공)
    반환 plan: kind, label, ball_type, landing(ft), field_by, throw_to(ft),
              bases, outs, double_play, sac_fly, error
    """
    runner_first = bases[0]

    # 파울 (타구 각도)
    if abs(spray_deg) > F.FOUL_DEG:
        return _foul_plan(F.polar(80, spray_deg))

    fence = F.fence_dist(spray_deg)

    # ---------------------------------------------------- 땅볼
    if launch_deg < 10:
        rad = math.radians(spray_deg)
        dx, dy = math.sin(rad), math.cos(rad)
        roll = 90 + power * 190
        ballspeed = 95 + power * 80
        can = []
        for name in INFIELDERS:
            px, py = F.FIELDERS_HOME[name]
            proj = px * dx + py * dy
            perp = abs(px * dy - py * dx)
            if proj <= 6 or proj > roll:
                continue
            t = proj / ballspeed
            # 강한 타구일수록 옆을 빠르게 지나가 잡기 어려움(3-유간/1-2루간)
            reach = FIELDER_SPEED * t + 8 - power * 4
            if name == "투수":
                # 투수는 홈 정면축 바로 위에 있어 perp 가 항상 작게 나와
                # 그대로 두면 '가장 가까운 수비수' 판정에서 거의 항상 이겨버린다.
                # 실제로는 마운드 정면 강습타만 잡을 수 있으므로 커버 폭을 좁힌다.
                reach = min(reach, PITCHER_GROUND_REACH_FT)
            if perp <= reach:
                can.append((proj, name, t))
        if can:
            can.sort()
            proj, fielder, t = can[0]
            fpos = F.FIELDERS_HOME[fielder]
            # 실책
            if random.random() < 0.06:
                return dict(kind="error", label="실책 출루", ball_type="ground",
                            landing=fpos, field_by=fielder, throw_to=F.B1,
                            bases=1, outs=0, double_play=False,
                            sac_fly=False, error=True)
            throw_t = F.dist_ft(fpos, F.B1) / THROW_SPEED + RELEASE
            def_time = t + throw_t
            safe = def_time > RUN_HOME_TO_FIRST + random.uniform(-0.15, 0.15)
            # 병살: 2루 경유 더블플레이 (6-4-3 / 4-6-3 등)
            if (runner_first and outs < 2 and fielder != "투수"
                    and not safe and random.random() < 0.62):
                dp_code, dp_relay = _double_play_details(fielder)
                return dict(kind="out", label=f"병살타! ({dp_code})",
                            ball_type="ground", landing=fpos, field_by=fielder,
                            throw_to=F.B1, dp_mid=F.B2, dp_relay=dp_relay,
                            dp_code=dp_code, bases=0, outs=2, double_play=True,
                            sac_fly=False, error=False)
            if safe:
                return dict(kind="hit", label="내야 안타!", ball_type="ground",
                            landing=fpos, field_by=fielder, throw_to=F.B1,
                            bases=1, outs=0, double_play=False,
                            sac_fly=False, error=False)
            # 투수 땅볼: 대부분 1루 송구(타자 아웃, 1루 주자 2루 진루)
            if fielder == "투수":
                return dict(kind="out", label=f"땅볼 아웃 ({fielder}→1루)",
                            ball_type="ground", landing=fpos, field_by=fielder,
                            throw_to=F.B1, out_at_first=True, bases=0, outs=1,
                            double_play=False, sac_fly=False, error=False)
            # 2아웃이면 1루 송구가 일반적
            if runner_first and outs >= 2:
                return dict(kind="out", label=f"땅볼 아웃 ({fielder}→1루)",
                            ball_type="ground", landing=fpos, field_by=fielder,
                            throw_to=F.B1, out_at_first=True, bases=0, outs=1,
                            double_play=False, sac_fly=False, error=False)
            # 1루 주자 있음 → 2루 포스 아웃 송구, 타자 1루 도착
            if runner_first:
                relay = _fc_second_cover(fielder)
                return dict(kind="out", label=f"땅볼 아웃 ({fielder}→2루)",
                            ball_type="ground", landing=fpos, field_by=fielder,
                            throw_to=F.B2, force_out_2nd=True, fc_relay=relay,
                            bases=0, outs=1, double_play=False,
                            sac_fly=False, error=False)
            return dict(kind="out", label=f"땅볼 아웃 ({fielder})",
                        ball_type="ground", landing=fpos, field_by=fielder,
                        throw_to=F.B1, out_at_first=True, bases=0, outs=1,
                        double_play=False, sac_fly=False, error=False)
        # 내야 사이로 빠지는 안타
        roll_pt = F.polar(min(roll + 40, fence - 10), spray_deg)
        if F.is_foul_point(roll_pt):
            return _foul_plan(roll_pt)
        bases_n = 2 if power > 0.58 and abs(spray_deg) > 15 else 1
        return dict(kind="hit", label="안타!" if bases_n == 1 else "2루타!",
                    ball_type="ground", landing=roll_pt,
                    field_by=_outfielder_for(spray_deg), throw_to=None,
                    bases=bases_n, outs=0, double_play=False,
                    sac_fly=False, error=False)

    # ---------------------------------------------------- 뜬공 / 라인드라이브 / 팝업
    if launch_deg >= 50:  # 팝업
        carry = 90 + power * 90
        land = F.polar(carry, spray_deg)
        if F.is_foul_point(land):
            return _foul_plan(land)
        best, caught = _nearest_catcher(land, 3.0, radius=10)
        return dict(kind="out", label=f"뜬공 아웃 ({best})", ball_type="fly",
                    landing=land, field_by=best, throw_to=None, bases=0,
                    outs=1, double_play=False, sac_fly=False, error=False)

    liner = launch_deg < 25
    if liner:
        carry = 130 + power * 180
        hang = 0.6 + power * 0.5
        radius = 12
    else:  # 뜬공
        lb = max(0.4, 1 - ((launch_deg - 32) / 30.0) ** 2)
        carry = (160 + power * 315) * lb
        hang = 1.3 + (launch_deg / 45.0) * 2.0 + power * 0.5
        radius = 10

    # 홈런
    if not liner and carry >= fence:
        land = F.polar(fence + 20, spray_deg)
        hr_title, hr_sub = _hr_presentation(bases)
        return dict(kind="hr", label=hr_title, hr_title=hr_title, hr_sub=hr_sub,
                    ball_type="fly", landing=land,
                    field_by=None, throw_to=None, bases=4, outs=0,
                    double_play=False, sac_fly=False, error=False)

    land = F.polar(carry, spray_deg)
    if F.is_foul_point(land):
        return _foul_plan(land)

    # 강한 직선타가 내야수 정면으로 향하면 정면 캐치(내야 직선타 아웃)
    if liner:
        snag = _infield_liner_snag(spray_deg, carry)
        if snag:
            return dict(kind="out", label=f"{snag} 직선타 아웃!",
                        ball_type="liner", landing=F.FIELDERS_HOME[snag],
                        field_by=snag, throw_to=None, bases=0, outs=1,
                        double_play=False, sac_fly=False, error=False)

    # 짧은 라이너: 내야수가 먼저 처리(내야 직선타 vs 땅볼과 별도)
    if liner and carry < 175:
        ifield = {n: F.FIELDERS_HOME[n] for n in INFIELDERS}
        best, caught = _nearest_catcher(land, hang, radius=radius + 2,
                                        candidates=ifield)
    else:
        best, caught = None, False
    if not caught:
        best, caught = _nearest_catcher(land, hang, radius=radius)
    if caught:
        # 깊은 뜬공 태그업·희생플라이는 2아웃 전에만
        deep = (not liner) and carry > 230
        can_tag = deep and outs < 2
        if can_tag and bases[2]:
            label = "희생플라이!"
        elif liner and best in INFIELDER_SET:
            label = f"내야 직선타 아웃 ({best})"
        else:
            label = f"뜬공 아웃 ({best})"
        return dict(kind="out", label=label, ball_type="fly", landing=land,
                    field_by=best, throw_to=None, bases=0, outs=1,
                    double_play=False, sac_fly=can_tag and bases[2],
                    tag_up=can_tag, error=False)

    # 안타(뜬공/라인성): 거리로 루타
    if carry >= fence * 0.84 and random.random() < 0.42:
        bases_n, label = 3, "3루타!"
    elif carry >= fence * 0.68:
        bases_n, label = 2, "2루타!"
    else:
        bases_n, label = 1, "안타!"
    return dict(kind="hit", label=label, ball_type="fly", landing=land,
                field_by=best, throw_to=None, bases=bases_n, outs=0,
                double_play=False, sac_fly=False, error=False)


_LINER_SNAG_FIELDERS = ("1루수", "2루수", "유격수", "3루수")
_LINER_SNAG_PERP_FT = 2.7


def _infield_liner_snag(spray_deg, carry):
    """강한 직선타의 궤적이 내야수 정면 근처를 지나가면 정면에서 캐치해 아웃.

    (하드히트 직선타는 원래 뻗어나가는 거리가 멀어 '뛰어가서 잡는' 판정으로는
    내야수가 절대 따라잡을 수 없다 — 실제로는 정면으로 오는 타구를 서서 잡는
    경우이므로 궤적과 수비수 위치의 수직거리로 따로 판정한다.)
    """
    rad = math.radians(spray_deg)
    dx, dy = math.sin(rad), math.cos(rad)
    best_name, best_perp = None, 1e9
    for name in _LINER_SNAG_FIELDERS:
        px, py = F.FIELDERS_HOME[name]
        proj = px * dx + py * dy
        if proj <= 10 or proj > carry:
            continue
        perp = abs(px * dy - py * dx)
        if perp < best_perp:
            best_perp, best_name = perp, name
    if best_name is not None and best_perp <= _LINER_SNAG_PERP_FT:
        return best_name
    return None


def _outfielder_for(spray_deg):
    if spray_deg < -15:
        return "좌익수"
    if spray_deg > 15:
        return "우익수"
    return "중견수"
