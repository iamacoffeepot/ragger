package dev.ragger.plugin.ui;

import java.awt.*;

/**
 * Shared color palette and font stack for all Ragger UI components.
 */
public final class RaggerTheme {

    private RaggerTheme() {}

    // ── Background ──────────────────────────────────────────────────────
    public static final Color BG           = new Color(0x18, 0x18, 0x1E);
    public static final Color BG_ALPHA     = new Color(0x18, 0x18, 0x1E, 0xE8);
    public static final Color BG_RAISED    = new Color(0x22, 0x22, 0x2A);
    public static final Color BG_CODE      = new Color(0x2A, 0x2A, 0x35, 0xCC);
    public static final Color BG_TABLE_HDR = new Color(0x2A, 0x2A, 0x38, 0xCC);
    public static final Color INPUT_BG     = new Color(0x22, 0x22, 0x2A, 0xEE);

    // ── Foreground ──────────────────────────────────────────────────────
    public static final Color TEXT         = new Color(0xE0, 0xE0, 0xE0);
    public static final Color TEXT_DIM     = new Color(0x99, 0x99, 0x99);
    public static final Color TEXT_DIMMER  = new Color(0x88, 0x88, 0x88);
    public static final Color ACCENT       = new Color(0xFF, 0xB3, 0x47);
    public static final Color CODE         = new Color(0xA8, 0xD8, 0xF0);
    public static final Color QUOTE        = new Color(0xAA, 0xAA, 0xAA);

    // ── Borders / Rules ─────────────────────────────────────────────────
    public static final Color BORDER       = new Color(0x55, 0x55, 0x66);
    public static final Color TABLE_BORDER = new Color(0x44, 0x44, 0x55);

    // ── Fonts ───────────────────────────────────────────────────────────
    public static final Font FONT;
    public static final Font FONT_BOLD;
    public static final Font FONT_ITALIC;
    public static final Font FONT_BOLD_ITALIC;
    public static final Font FONT_HEADER;
    public static final Font FONT_SMALL;

    static {
        Font regular = loadFont("/dev/ragger/plugin/fonts/MesloLGS-Regular.ttf", Font.PLAIN);
        Font bold    = loadFont("/dev/ragger/plugin/fonts/MesloLGS-Bold.ttf", Font.BOLD);
        Font italic  = loadFont("/dev/ragger/plugin/fonts/MesloLGS-Italic.ttf", Font.ITALIC);
        Font bi      = loadFont("/dev/ragger/plugin/fonts/MesloLGS-BoldItalic.ttf", Font.BOLD | Font.ITALIC);

        FONT            = regular.deriveFont(12f);
        FONT_BOLD       = bold.deriveFont(12f);
        FONT_ITALIC     = italic.deriveFont(12f);
        FONT_BOLD_ITALIC = bi.deriveFont(12f);
        FONT_HEADER     = bold.deriveFont(14f);
        FONT_SMALL      = regular.deriveFont(11f);
    }

    private static Font loadFont(String resource, int fallbackStyle) {
        try (var is = RaggerTheme.class.getResourceAsStream(resource)) {
            if (is != null) {
                Font font = Font.createFont(Font.TRUETYPE_FONT, is);
                GraphicsEnvironment.getLocalGraphicsEnvironment().registerFont(font);
                return font;
            }
        } catch (Exception e) {
            // fall through
        }
        return new Font(Font.MONOSPACED, fallbackStyle, 12);
    }

    /**
     * Hex string for use in HTML/CSS style attributes.
     */
    public static String hex(Color c) {
        return String.format("#%02x%02x%02x", c.getRed(), c.getGreen(), c.getBlue());
    }
}
