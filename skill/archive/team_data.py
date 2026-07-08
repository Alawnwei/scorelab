"""
球队战术数据库
基于《足球分析.md》中总结的球队战术风格和特性
"""

from enum import Enum
from dataclasses import dataclass, field
from typing import List, Optional


class TacticalStyle(Enum):
    """三大核心战术风格"""
    COUNTER_ATTACK = "防守反击"        # 低位密集防守 + 快速反击
    POSSESSION = "传控"                # 控场节奏型，传控为主
    HIGH_PRESS = "高位逼抢"            # 压迫式打法，高位逼抢
    HYBRID = "复合型"                  # 混合型打法


class TeamStrength(Enum):
    """球队实力层级"""
    TOP = "顶级强队"
    STRONG = "次一流强队"
    MIDDLE = "中游球队"
    WEAK = "弱队"


@dataclass
class Team:
    """球队信息"""
    name: str                          # 球队名称
    tactical_styles: List[TacticalStyle]  # 战术风格（可混合）
    primary_style: TacticalStyle       # 主导风格
    strength: TeamStrength = TeamStrength.MIDDLE
    win_rate: float = 50.0             # 赢盘率（%）
    corner_tendency: Optional[str] = None  # 角球倾向："刷角强" / "刷角弱" / None
    notes: str = ""                    # 备注

    # 战术特性
    good_at_set_pieces: bool = False   # 擅长定位球/头球
    good_at_counter: bool = False      # 擅长防反
    good_at_possession: bool = False   # 擅长传控
    defensive_stability: float = 5.0   # 防守稳定性 1-10
    attacking_power: float = 5.0       # 进攻火力 1-10
    aerial_advantage: bool = False     # 高空优势
    physical_advantage: bool = False   # 身体对抗优势


# ============================================================
# 球队数据库
# 根据文档中提到的球队整理
# ============================================================

TEAMS_DB: dict = {}

def _init_teams():
    """初始化球队数据库"""
    global TEAMS_DB
    teams = [
        # ---- 高位逼抢型球队 ----
        Team("德国", [TacticalStyle.HIGH_PRESS], TacticalStyle.HIGH_PRESS,
             TeamStrength.STRONG, corner_tendency="刷角强",
             notes="高位逼抢压迫式打法代表"),
        Team("韩国", [TacticalStyle.HIGH_PRESS], TacticalStyle.HIGH_PRESS,
             TeamStrength.MIDDLE, corner_tendency="刷角强",
             notes="高位逼抢，凶狠性足球风格"),
        Team("加拿大", [TacticalStyle.HIGH_PRESS, TacticalStyle.COUNTER_ATTACK],
             TacticalStyle.HIGH_PRESS, TeamStrength.MIDDLE, win_rate=50.0,
             corner_tendency="刷角强",
             notes="青春风暴，现代快速逼抢风格，高位逼抢+边路冲击"),

        # ---- 复合型（传控+高位逼抢） ----
        Team("法国", [TacticalStyle.HYBRID], TacticalStyle.HIGH_PRESS,
             TeamStrength.TOP, corner_tendency="刷角强",
             notes="复合型打法，传控+高位逼抢混合，边路冲击强",
             attacking_power=9.0, defensive_stability=8.0),
        Team("阿根廷", [TacticalStyle.HYBRID], TacticalStyle.HIGH_PRESS,
             TeamStrength.TOP, corner_tendency="刷角强",
             notes="高压逼抢+防守反击混合，灵活多变",
             attacking_power=9.0),
        Team("荷兰", [TacticalStyle.HYBRID, TacticalStyle.POSSESSION],
             TacticalStyle.POSSESSION, TeamStrength.STRONG,
             notes="追求攻守平衡，后防稳定，身体对抗和高空优势",
             defensive_stability=8.0, aerial_advantage=True, physical_advantage=True),

        # ---- 传控型球队 ----
        Team("西班牙", [TacticalStyle.POSSESSION], TacticalStyle.POSSESSION,
             TeamStrength.TOP,
             notes="典型传控球队，高控球率，中场调度"),
        Team("瑞士", [TacticalStyle.POSSESSION], TacticalStyle.POSSESSION,
             TeamStrength.MIDDLE,
             notes="控场类，不走大开大合，后防顶，遇弱不强遇强不弱",
             defensive_stability=8.0, attacking_power=5.5),
        Team("日本", [TacticalStyle.POSSESSION, TacticalStyle.COUNTER_ATTACK],
             TacticalStyle.POSSESSION, TeamStrength.STRONG,
             win_rate=60.0,
             notes="传控+小范围穿插+低位防守+快速反击，灵动型技术特点",
             good_at_possession=True, good_at_counter=True),

        # ---- 防守反击型球队 ----
        Team("塞内加尔", [TacticalStyle.COUNTER_ATTACK], TacticalStyle.COUNTER_ATTACK,
             TeamStrength.MIDDLE, corner_tendency="刷角强",
             notes="防反利落，中场拦截好，反击速度快，边路有爆点",
             good_at_counter=True, defensive_stability=7.5),
        Team("埃及", [TacticalStyle.COUNTER_ATTACK], TacticalStyle.COUNTER_ATTACK,
             TeamStrength.MIDDLE, win_rate=46.0,
             notes="低位不乱防守体系，防守好，球员默契感好，中场调度差",
             good_at_counter=True, defensive_stability=7.5),
        Team("波黑", [TacticalStyle.COUNTER_ATTACK], TacticalStyle.COUNTER_ATTACK,
             TeamStrength.MIDDLE, win_rate=50.0,
             notes="防反为主，定位球好，球队韧性强，骨头难啃",
             good_at_counter=True, good_at_set_pieces=True),
        Team("卡塔尔", [TacticalStyle.COUNTER_ATTACK, TacticalStyle.POSSESSION],
             TacticalStyle.COUNTER_ATTACK, TeamStrength.WEAK,
             notes="学传控不精髓，防守为主，防空防渗透差",
             defensive_stability=4.0),

        # ---- 其他球队 ----
        Team("比利时", [TacticalStyle.POSSESSION, TacticalStyle.HYBRID],
             TacticalStyle.POSSESSION, TeamStrength.STRONG, win_rate=40.0,
             notes="抗压能力没问题，控制比赛结构不如以前，前场丰富性减少，像加强版瑞士",
             defensive_stability=7.0, attacking_power=7.5),
        Team("阿尔及利亚", [TacticalStyle.HIGH_PRESS, TacticalStyle.COUNTER_ATTACK],
             TacticalStyle.HIGH_PRESS, TeamStrength.MIDDLE,
             notes="走逼抢路子，非洲小阿根廷"),
        Team("美国", [TacticalStyle.HIGH_PRESS], TacticalStyle.HIGH_PRESS,
             TeamStrength.MIDDLE,
             notes="现代快速打法"),
        Team("巴拉圭", [TacticalStyle.COUNTER_ATTACK], TacticalStyle.COUNTER_ATTACK,
             TeamStrength.MIDDLE, win_rate=70.0,
             notes="近期盘王，买它方向10场收7场"),
        Team("乌拉圭", [TacticalStyle.HIGH_PRESS, TacticalStyle.COUNTER_ATTACK],
             TacticalStyle.COUNTER_ATTACK, TeamStrength.STRONG),
        Team("伊朗", [TacticalStyle.COUNTER_ATTACK], TacticalStyle.COUNTER_ATTACK,
             TeamStrength.MIDDLE,
             notes="防守为主"),
    ]

    for team in teams:
        TEAMS_DB[team.name] = team

    # 额外添加别名
    TEAMS_DB["塞内加爾"] = TEAMS_DB["塞内加尔"]


def get_team(name: str) -> Optional[Team]:
    """按名称获取球队"""
    if not TEAMS_DB:
        _init_teams()
    return TEAMS_DB.get(name)


def search_team(keyword: str) -> List[Team]:
    """模糊搜索球队"""
    if not TEAMS_DB:
        _init_teams()
    results = []
    for name, team in TEAMS_DB.items():
        if keyword in name or keyword.lower() in name.lower():
            if team not in results:  # 避免别名重复
                results.append(team)
    return results


def list_all_teams() -> List[str]:
    """列出所有球队名称"""
    if not TEAMS_DB:
        _init_teams()
    seen = set()
    names = []
    for name in TEAMS_DB:
        if name not in seen:
            seen.add(name)
            names.append(name)
    return sorted(names)


def get_teams_by_style(style: TacticalStyle) -> List[Team]:
    """按战术风格获取球队列表"""
    if not TEAMS_DB:
        _init_teams()
    return [t for t in TEAMS_DB.values() if style in t.tactical_styles]


# 初始化
_init_teams()
