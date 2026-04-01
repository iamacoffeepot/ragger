from enum import Enum


class Skill(str, Enum):
    ATTACK = "Attack"
    STRENGTH = "Strength"
    DEFENCE = "Defence"
    RANGED = "Ranged"
    PRAYER = "Prayer"
    MAGIC = "Magic"
    RUNECRAFT = "Runecraft"
    CONSTRUCTION = "Construction"
    HITPOINTS = "Hitpoints"
    AGILITY = "Agility"
    HERBLORE = "Herblore"
    THIEVING = "Thieving"
    CRAFTING = "Crafting"
    FLETCHING = "Fletching"
    SLAYER = "Slayer"
    HUNTER = "Hunter"
    MINING = "Mining"
    SMITHING = "Smithing"
    FISHING = "Fishing"
    COOKING = "Cooking"
    FIREMAKING = "Firemaking"
    WOODCUTTING = "Woodcutting"
    FARMING = "Farming"


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


class DiaryTier(str, Enum):
    EASY = "Easy"
    MEDIUM = "Medium"
    HARD = "Hard"
    ELITE = "Elite"
