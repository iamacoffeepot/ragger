package dev.ragger.plugin.scripting;

import net.runelite.api.Prayer;

/**
 * Lua binding for prayer enum constants.
 * Exposed as the global "prayer" table in Lua scripts.
 *
 * Usage: combat:prayer_active(prayer.PROTECT_FROM_MELEE)
 */
public class PrayerApi {

    // Standard prayers
    public final Prayer THICK_SKIN = Prayer.THICK_SKIN;
    public final Prayer BURST_OF_STRENGTH = Prayer.BURST_OF_STRENGTH;
    public final Prayer CLARITY_OF_THOUGHT = Prayer.CLARITY_OF_THOUGHT;
    public final Prayer SHARP_EYE = Prayer.SHARP_EYE;
    public final Prayer MYSTIC_WILL = Prayer.MYSTIC_WILL;
    public final Prayer ROCK_SKIN = Prayer.ROCK_SKIN;
    public final Prayer SUPERHUMAN_STRENGTH = Prayer.SUPERHUMAN_STRENGTH;
    public final Prayer IMPROVED_REFLEXES = Prayer.IMPROVED_REFLEXES;
    public final Prayer RAPID_RESTORE = Prayer.RAPID_RESTORE;
    public final Prayer RAPID_HEAL = Prayer.RAPID_HEAL;
    public final Prayer PROTECT_ITEM = Prayer.PROTECT_ITEM;
    public final Prayer HAWK_EYE = Prayer.HAWK_EYE;
    public final Prayer MYSTIC_LORE = Prayer.MYSTIC_LORE;
    public final Prayer STEEL_SKIN = Prayer.STEEL_SKIN;
    public final Prayer ULTIMATE_STRENGTH = Prayer.ULTIMATE_STRENGTH;
    public final Prayer INCREDIBLE_REFLEXES = Prayer.INCREDIBLE_REFLEXES;
    public final Prayer PROTECT_FROM_MAGIC = Prayer.PROTECT_FROM_MAGIC;
    public final Prayer PROTECT_FROM_MISSILES = Prayer.PROTECT_FROM_MISSILES;
    public final Prayer PROTECT_FROM_MELEE = Prayer.PROTECT_FROM_MELEE;
    public final Prayer EAGLE_EYE = Prayer.EAGLE_EYE;
    public final Prayer MYSTIC_MIGHT = Prayer.MYSTIC_MIGHT;
    public final Prayer RETRIBUTION = Prayer.RETRIBUTION;
    public final Prayer REDEMPTION = Prayer.REDEMPTION;
    public final Prayer SMITE = Prayer.SMITE;
    public final Prayer CHIVALRY = Prayer.CHIVALRY;
    public final Prayer DEADEYE = Prayer.DEADEYE;
    public final Prayer MYSTIC_VIGOUR = Prayer.MYSTIC_VIGOUR;
    public final Prayer PIETY = Prayer.PIETY;
    public final Prayer PRESERVE = Prayer.PRESERVE;
    public final Prayer RIGOUR = Prayer.RIGOUR;
    public final Prayer AUGURY = Prayer.AUGURY;

    // Ruinous Powers
    public final Prayer RP_REJUVENATION = Prayer.RP_REJUVENATION;
    public final Prayer RP_ANCIENT_STRENGTH = Prayer.RP_ANCIENT_STRENGTH;
    public final Prayer RP_ANCIENT_SIGHT = Prayer.RP_ANCIENT_SIGHT;
    public final Prayer RP_ANCIENT_WILL = Prayer.RP_ANCIENT_WILL;
    public final Prayer RP_PROTECT_ITEM = Prayer.RP_PROTECT_ITEM;
    public final Prayer RP_RUINOUS_GRACE = Prayer.RP_RUINOUS_GRACE;
    public final Prayer RP_DAMPEN_MAGIC = Prayer.RP_DAMPEN_MAGIC;
    public final Prayer RP_DAMPEN_RANGED = Prayer.RP_DAMPEN_RANGED;
    public final Prayer RP_DAMPEN_MELEE = Prayer.RP_DAMPEN_MELEE;
    public final Prayer RP_TRINITAS = Prayer.RP_TRINITAS;
    public final Prayer RP_BERSERKER = Prayer.RP_BERSERKER;
    public final Prayer RP_PURGE = Prayer.RP_PURGE;
    public final Prayer RP_METABOLISE = Prayer.RP_METABOLISE;
    public final Prayer RP_REBUKE = Prayer.RP_REBUKE;
    public final Prayer RP_VINDICATION = Prayer.RP_VINDICATION;
    public final Prayer RP_DECIMATE = Prayer.RP_DECIMATE;
    public final Prayer RP_ANNIHILATE = Prayer.RP_ANNIHILATE;
    public final Prayer RP_VAPORISE = Prayer.RP_VAPORISE;
    public final Prayer RP_FUMUS_VOW = Prayer.RP_FUMUS_VOW;
    public final Prayer RP_UMBRA_VOW = Prayer.RP_UMBRA_VOW;
    public final Prayer RP_CRUORS_VOW = Prayer.RP_CRUORS_VOW;
    public final Prayer RP_GLACIES_VOW = Prayer.RP_GLACIES_VOW;
    public final Prayer RP_WRATH = Prayer.RP_WRATH;
    public final Prayer RP_INTENSIFY = Prayer.RP_INTENSIFY;
}
