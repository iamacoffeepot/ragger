from enum import Enum


class Skill(int, Enum):
    ATTACK = 0
    STRENGTH = 1
    DEFENCE = 2
    RANGED = 3
    PRAYER = 4
    MAGIC = 5
    RUNECRAFT = 6
    CONSTRUCTION = 7
    HITPOINTS = 8
    AGILITY = 9
    HERBLORE = 10
    THIEVING = 11
    CRAFTING = 12
    FLETCHING = 13
    SLAYER = 14
    HUNTER = 15
    MINING = 16
    SMITHING = 17
    FISHING = 18
    COOKING = 19
    FIREMAKING = 20
    WOODCUTTING = 21
    FARMING = 22

    @property
    def label(self) -> str:
        return SKILL_LABELS[self]

    @property
    def mask(self) -> int:
        return 1 << self.value

    @classmethod
    def from_label(cls, label: str) -> "Skill":
        return _SKILL_LABEL_LOOKUP[label.lower()]


SKILL_LABELS: dict["Skill", str] = {
    Skill.ATTACK: "Attack",
    Skill.STRENGTH: "Strength",
    Skill.DEFENCE: "Defence",
    Skill.RANGED: "Ranged",
    Skill.PRAYER: "Prayer",
    Skill.MAGIC: "Magic",
    Skill.RUNECRAFT: "Runecraft",
    Skill.CONSTRUCTION: "Construction",
    Skill.HITPOINTS: "Hitpoints",
    Skill.AGILITY: "Agility",
    Skill.HERBLORE: "Herblore",
    Skill.THIEVING: "Thieving",
    Skill.CRAFTING: "Crafting",
    Skill.FLETCHING: "Fletching",
    Skill.SLAYER: "Slayer",
    Skill.HUNTER: "Hunter",
    Skill.MINING: "Mining",
    Skill.SMITHING: "Smithing",
    Skill.FISHING: "Fishing",
    Skill.COOKING: "Cooking",
    Skill.FIREMAKING: "Firemaking",
    Skill.WOODCUTTING: "Woodcutting",
    Skill.FARMING: "Farming",
}

_SKILL_LABEL_LOOKUP: dict[str, Skill] = {v.lower(): k for k, v in SKILL_LABELS.items()}

ALL_SKILLS_MASK = (1 << len(Skill)) - 1

COMBAT_SKILLS_MASK = (
    Skill.ATTACK.mask
    | Skill.STRENGTH.mask
    | Skill.DEFENCE.mask
    | Skill.HITPOINTS.mask
    | Skill.RANGED.mask
    | Skill.MAGIC.mask
    | Skill.PRAYER.mask
)


class Region(int, Enum):
    GENERAL = 0
    ASGARNIA = 1
    DESERT = 2
    FREMENNIK = 3
    KANDARIN = 4
    KARAMJA = 5
    KOUREND = 6
    MISTHALIN = 7
    MORYTANIA = 8
    TIRANNWN = 9
    VARLAMORE = 10
    WILDERNESS = 11

    @property
    def label(self) -> str:
        return REGION_LABELS[self]

    @property
    def mask(self) -> int:
        return 1 << self.value

    @classmethod
    def from_label(cls, label: str) -> "Region":
        return _REGION_LABEL_LOOKUP[label.lower()]


REGION_LABELS: dict["Region", str] = {
    Region.GENERAL: "General",
    Region.ASGARNIA: "Asgarnia",
    Region.DESERT: "Desert",
    Region.FREMENNIK: "Fremennik",
    Region.KANDARIN: "Kandarin",
    Region.KARAMJA: "Karamja",
    Region.KOUREND: "Kourend",
    Region.MISTHALIN: "Misthalin",
    Region.MORYTANIA: "Morytania",
    Region.TIRANNWN: "Tirannwn",
    Region.VARLAMORE: "Varlamore",
    Region.WILDERNESS: "Wilderness",
}

_REGION_LABEL_LOOKUP: dict[str, Region] = {v.lower(): k for k, v in REGION_LABELS.items()}

ALL_REGIONS_MASK = (1 << len(Region)) - 1


class TaskDifficulty(int, Enum):
    EASY = 0
    MEDIUM = 1
    HARD = 2
    ELITE = 3
    MASTER = 4

    @property
    def label(self) -> str:
        return TASK_DIFFICULTY_LABELS[self]

    @property
    def points(self) -> int:
        return TASK_DIFFICULTY_POINTS[self]


TASK_DIFFICULTY_LABELS: dict["TaskDifficulty", str] = {
    TaskDifficulty.EASY: "Easy",
    TaskDifficulty.MEDIUM: "Medium",
    TaskDifficulty.HARD: "Hard",
    TaskDifficulty.ELITE: "Elite",
    TaskDifficulty.MASTER: "Master",
}

TASK_DIFFICULTY_POINTS: dict["TaskDifficulty", int] = {
    TaskDifficulty.EASY: 10,
    TaskDifficulty.MEDIUM: 30,
    TaskDifficulty.HARD: 80,
    TaskDifficulty.ELITE: 200,
    TaskDifficulty.MASTER: 400,
}


class DiaryLocation(str, Enum):
    ARDOUGNE = "Ardougne"
    DESERT = "Desert"
    FALADOR = "Falador"
    FREMENNIK = "Fremennik"
    KANDARIN = "Kandarin"
    KARAMJA = "Karamja"
    KOUREND_KEBOS = "Kourend & Kebos"
    LUMBRIDGE_DRAYNOR = "Lumbridge & Draynor"
    MORYTANIA = "Morytania"
    VARROCK = "Varrock"
    WESTERN_PROVINCES = "Western Provinces"
    WILDERNESS = "Wilderness"

    def xp_reward(self, tier: "DiaryTier") -> int:
        if self == DiaryLocation.KARAMJA:
            return _KARAMJA_DIARY_XP[tier]
        return _STANDARD_DIARY_XP[tier]

    def min_level(self, tier: "DiaryTier") -> int:
        if self == DiaryLocation.KARAMJA:
            return _KARAMJA_DIARY_MIN_LEVEL[tier]
        return _STANDARD_DIARY_MIN_LEVEL[tier]


class DiaryTier(str, Enum):
    EASY = "Easy"
    MEDIUM = "Medium"
    HARD = "Hard"
    ELITE = "Elite"


_STANDARD_DIARY_XP: dict[DiaryTier, int] = {
    DiaryTier.EASY: 2_500,
    DiaryTier.MEDIUM: 7_500,
    DiaryTier.HARD: 15_000,
    DiaryTier.ELITE: 50_000,
}

_KARAMJA_DIARY_XP: dict[DiaryTier, int] = {
    DiaryTier.EASY: 1_000,
    DiaryTier.MEDIUM: 5_000,
    DiaryTier.HARD: 10_000,
    DiaryTier.ELITE: 50_000,
}

_STANDARD_DIARY_MIN_LEVEL: dict[DiaryTier, int] = {
    DiaryTier.EASY: 30,
    DiaryTier.MEDIUM: 40,
    DiaryTier.HARD: 50,
    DiaryTier.ELITE: 70,
}

_KARAMJA_DIARY_MIN_LEVEL: dict[DiaryTier, int] = {
    DiaryTier.EASY: 1,
    DiaryTier.MEDIUM: 30,
    DiaryTier.HARD: 40,
    DiaryTier.ELITE: 70,
}


class ActionTriggerType(int, Enum):
    """Action trigger types corresponding to client interaction packets (oploc, opnpc, etc.)."""

    CLICK_OBJECT = 0
    CLICK_NPC = 1
    CLICK_ITEM = 2
    USE_ITEM_ON_OBJECT = 3
    USE_ITEM_ON_NPC = 4
    USE_ITEM_ON_ITEM = 5
    CLICK_WIDGET = 6
    WIDGET_ON_ITEM = 7

    @property
    def mask(self) -> int:
        return 1 << self.value

    @property
    def label(self) -> str:
        return TRIGGER_TYPE_LABELS[self]


TRIGGER_TYPE_LABELS: dict["ActionTriggerType", str] = {
    ActionTriggerType.CLICK_OBJECT: "Click object",
    ActionTriggerType.CLICK_NPC: "Click NPC",
    ActionTriggerType.CLICK_ITEM: "Click item",
    ActionTriggerType.USE_ITEM_ON_OBJECT: "Use item on object",
    ActionTriggerType.USE_ITEM_ON_NPC: "Use item on NPC",
    ActionTriggerType.USE_ITEM_ON_ITEM: "Use item on item",
    ActionTriggerType.CLICK_WIDGET: "Click widget",
    ActionTriggerType.WIDGET_ON_ITEM: "Widget on item",
}


class Facility(int, Enum):
    BANK = 0
    FURNACE = 1
    ANVIL = 2
    RANGE = 3
    ALTAR = 4
    SPINNING_WHEEL = 5
    LOOM = 6

    @property
    def mask(self) -> int:
        return 1 << self.value

    @property
    def label(self) -> str:
        return FACILITY_LABELS[self]


FACILITY_LABELS: dict["Facility", str] = {
    Facility.BANK: "Bank",
    Facility.FURNACE: "Furnace",
    Facility.ANVIL: "Anvil",
    Facility.RANGE: "Range",
    Facility.ALTAR: "Altar",
    Facility.SPINNING_WHEEL: "Spinning wheel",
    Facility.LOOM: "Loom",
}


class Immunity(int, Enum):
    POISON = 0
    VENOM = 1
    CANNON = 2
    THRALL = 3
    BURN = 4

    @property
    def mask(self) -> int:
        return 1 << self.value

    @property
    def label(self) -> str:
        return IMMUNITY_LABELS[self]


IMMUNITY_LABELS: dict["Immunity", str] = {
    Immunity.POISON: "Poison",
    Immunity.VENOM: "Venom",
    Immunity.CANNON: "Cannon",
    Immunity.THRALL: "Thrall",
    Immunity.BURN: "Burn",
}


MAP_LINK_ANYWHERE = "ANYWHERE"


class MapSquareType(str, Enum):
    COLOR = "color"
    COLLISION = "collision"
    WATER = "water"


class MapLinkType(str, Enum):
    ENTRANCE = "entrance"
    EXIT = "exit"
    FAIRY_RING = "fairy_ring"
    CHARTER_SHIP = "charter_ship"
    SPIRIT_TREE = "spirit_tree"
    GNOME_GLIDER = "gnome_glider"
    CANOE = "canoe"
    TELEPORT = "teleport"
    MINECART = "minecart"
    SHIP = "ship"
    QUETZAL = "quetzal"
    WALKABLE = "walkable"
    NPC_TRANSPORT = "npc_transport"


class ShopType(str, Enum):
    GENERAL = "General store"
    ARCHERY = "Archery shop"
    AXE = "Axe shop"
    CHAINBODY = "Chainbody shop"
    HELMET = "Helmet shop"
    MACE = "Mace shop"
    PLATEBODY = "Platebody shop"
    PLATELEGS = "Platelegs shop"
    PLATESKIRT = "Plateskirt shop"
    SCIMITAR = "Scimitar shop"
    SHIELD = "Shield shop"
    SWORD = "Sword shop"
    AMULET = "Amulet shop"
    CANDLE = "Candle shop"
    CLOTHES = "Clothes shop"
    COOKING = "Cooking shop"
    CRAFTING = "Crafting shop"
    CROSSBOW = "Crossbow shop"
    JEWELLERY = "Jewellery shop"
    DYE = "Dye shop"
    FARMING = "Farming shop"
    FISHING = "Fishing shop"
    FOOD = "Food shop"
    FUR = "Fur trader"
    GEM = "Gem shop"
    MAGIC = "Magic shop"
    MINING = "Mining shop"
    SILK = "Silk shop"
    HERBLORE = "Herblore shop"
    HUNTER = "Hunter shop"
    KEBAB = "Kebab seller"
    SILVER = "Silver shop"
    SPICE = "Spice shop"
    STAFF = "Staff shop"
    VEGETABLE = "Vegetable shop"
    WINE = "Wine shop"
    BAR = "Bar"
    REWARDS = "Rewards shop"
    OTHER = "Other"

    @classmethod
    def from_label(cls, label: str) -> "ShopType":
        """Map a wiki 'special' field value to a ShopType."""
        if not label:
            return cls.OTHER
        cleaned = label.strip().lower()
        for member in cls:
            if member.value.lower() == cleaned:
                return member
        # Fuzzy matching for common variants
        if "general" in cleaned:
            return cls.GENERAL
        if "fish" in cleaned:
            return cls.FISHING
        if "archery" in cleaned or "ranged" in cleaned:
            return cls.ARCHERY
        if "herb" in cleaned:
            return cls.HERBLORE
        if "farm" in cleaned:
            return cls.FARMING
        if "craft" in cleaned:
            return cls.CRAFTING
        if "gem" in cleaned:
            return cls.GEM
        if "magic" in cleaned or "rune" in cleaned:
            return cls.MAGIC
        if "food" in cleaned or "cook" in cleaned:
            return cls.FOOD
        if "mining" in cleaned or "ore" in cleaned:
            return cls.MINING
        if "hunter" in cleaned:
            return cls.HUNTER
        if "bar" in cleaned or "pub" in cleaned or "inn" in cleaned:
            return cls.BAR
        if "reward" in cleaned:
            return cls.REWARDS
        if "cloth" in cleaned or "fashion" in cleaned:
            return cls.CLOTHES
        if "fur" in cleaned:
            return cls.FUR
        if "silk" in cleaned:
            return cls.SILK
        if "spice" in cleaned:
            return cls.SPICE
        if "staff" in cleaned:
            return cls.STAFF
        if "sword" in cleaned:
            return cls.SWORD
        if "shield" in cleaned:
            return cls.SHIELD
        if "helmet" in cleaned:
            return cls.HELMET
        if "jewel" in cleaned:
            return cls.JEWELLERY
        if "kebab" in cleaned:
            return cls.KEBAB
        if "wine" in cleaned:
            return cls.WINE
        if "axe" in cleaned:
            return cls.AXE
        if "silver" in cleaned:
            return cls.SILVER
        if "dye" in cleaned:
            return cls.DYE
        if "candle" in cleaned:
            return cls.CANDLE
        return cls.OTHER


class VariableType(str, Enum):
    VARP = "varp"
    VARBIT = "varbit"
    VARC_INT = "varc_int"
    VARC_STR = "varc_str"

    @classmethod
    def from_label(cls, label: str) -> "VariableType":
        cleaned = label.strip().lower()
        for member in cls:
            if member.value == cleaned:
                return member
        raise ValueError(f"Unknown variable type: {label}")


class ContentCategory(str, Enum):
    QUEST = "quest"
    SKILL = "skill"
    NPC = "npc"
    LOCATION = "location"
    ITEM = "item"
    MINIGAME = "minigame"
    ACTIVITY = "activity"

    @classmethod
    def from_label(cls, label: str) -> "ContentCategory":
        cleaned = label.strip().lower()
        for member in cls:
            if member.value == cleaned:
                return member
        raise ValueError(f"Unknown content category: {label}")


class FunctionalTag(str, Enum):
    PROGRESS = "progress"
    TOGGLE = "toggle"
    COUNTER = "counter"
    UI = "ui"
    CONFIG = "config"
    STORAGE = "storage"
    TIMER = "timer"
    COSMETIC = "cosmetic"

    @classmethod
    def from_label(cls, label: str) -> "FunctionalTag":
        cleaned = label.strip().lower()
        for member in cls:
            if member.value == cleaned:
                return member
        raise ValueError(f"Unknown functional tag: {label}")


class EquipmentSlot(str, Enum):
    HEAD = "head"
    WEAPON = "weapon"
    BODY = "body"
    LEGS = "legs"
    SHIELD = "shield"
    CAPE = "cape"
    HANDS = "hands"
    FEET = "feet"
    NECK = "neck"
    AMMO = "ammo"
    RING = "ring"

    @property
    def label(self) -> str:
        return EQUIPMENT_SLOT_LABELS[self]

    @classmethod
    def from_label(cls, label: str) -> "EquipmentSlot":
        if not label:
            raise ValueError("Empty equipment slot label")
        cleaned = label.strip().lower()
        if cleaned == "2h":
            return cls.WEAPON
        for member in cls:
            if member.value == cleaned:
                return member
        raise ValueError(f"Unknown equipment slot: {label}")


EQUIPMENT_SLOT_LABELS: dict["EquipmentSlot", str] = {
    EquipmentSlot.HEAD: "Head",
    EquipmentSlot.WEAPON: "Weapon",
    EquipmentSlot.BODY: "Body",
    EquipmentSlot.LEGS: "Legs",
    EquipmentSlot.SHIELD: "Shield",
    EquipmentSlot.CAPE: "Cape",
    EquipmentSlot.HANDS: "Hands",
    EquipmentSlot.FEET: "Feet",
    EquipmentSlot.NECK: "Neck",
    EquipmentSlot.AMMO: "Ammo",
    EquipmentSlot.RING: "Ring",
}


class CombatStyle(str, Enum):
    TWO_HANDED_SWORD = "2h Sword"
    AXE = "Axe"
    BANNER = "Banner"
    BLADED_STAFF = "Bladed Staff"
    BLASTER = "Blaster"
    BLUDGEON = "Bludgeon"
    BLUNT = "Blunt"
    BOW = "Bow"
    BULWARK = "Bulwark"
    CHINCHOMPAS = "Chinchompas"
    CLAW = "Claw"
    CROSSBOW = "Crossbow"
    GUN = "Gun"
    MULTI_STYLE = "Multi-Style"
    PICKAXE = "Pickaxe"
    POLEARM = "Polearm"
    POLESTAFF = "Polestaff"
    POWERED_STAFF = "Powered Staff"
    SALAMANDER = "Salamander"
    SCYTHE = "Scythe"
    SLASH_SWORD = "Slash Sword"
    SPEAR = "Spear"
    SPIKED = "Spiked"
    STAB_SWORD = "Stab Sword"
    STAFF = "Staff"
    THROWN = "Thrown"
    UNARMED = "Unarmed"
    WHIP = "Whip"

    @classmethod
    def from_label(cls, label: str) -> "CombatStyle":
        if not label:
            raise ValueError("Empty combat style label")
        cleaned = label.strip()
        for member in cls:
            if member.value.lower() == cleaned.lower():
                return member
        raise ValueError(f"Unknown combat style: {label}")


class ActivityType(str, Enum):
    MINIGAME = "Minigame"
    RANDOM_EVENT = "Random event"
    FORESTRY = "Forestry"
    RAID = "Raid"
    ACTIVITY = "Activity"
    BOSS = "Boss"
    DISTRACTION_AND_DIVERSION = "Distraction and Diversion"
    QUEST = "Quest"
    REWARD = "Reward"

    @classmethod
    def from_label(cls, label: str) -> "ActivityType":
        if not label:
            return cls.ACTIVITY
        cleaned = label.strip()
        for member in cls:
            if member.value.lower() == cleaned.lower():
                return member
        return cls.ACTIVITY
