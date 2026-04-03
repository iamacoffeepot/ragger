package dev.ragger.plugin.scripting;

import java.awt.*;
import java.util.ArrayList;
import java.util.List;
import java.util.function.Consumer;

/**
 * Lua binding for drawing overlays on the game screen.
 * Exposed as the global "overlay" table in Lua scripts.
 *
 * Draw commands are queued during on_render and executed by ScriptOverlay.
 */
public class OverlayApi {

    private final List<Consumer<Graphics2D>> commands = new ArrayList<>();

    public void text(int x, int y, String text, int rgb) {
        Color color = new Color(rgb);
        commands.add(g -> {
            g.setColor(color);
            g.drawString(text, x, y);
        });
    }

    public void text(int x, int y, String text) {
        text(x, y, text, 0xFFFFFF);
    }

    public void rect(int x, int y, int width, int height, int rgb) {
        Color color = new Color(rgb);
        commands.add(g -> {
            g.setColor(color);
            g.drawRect(x, y, width, height);
        });
    }

    public void fill_rect(int x, int y, int width, int height, int rgb) {
        Color color = new Color(rgb);
        commands.add(g -> {
            g.setColor(color);
            g.fillRect(x, y, width, height);
        });
    }

    public void line(int x1, int y1, int x2, int y2, int rgb) {
        Color color = new Color(rgb);
        commands.add(g -> {
            g.setColor(color);
            g.drawLine(x1, y1, x2, y2);
        });
    }

    public void circle(int x, int y, int radius, int rgb) {
        Color color = new Color(rgb);
        commands.add(g -> {
            g.setColor(color);
            g.drawOval(x - radius, y - radius, radius * 2, radius * 2);
        });
    }

    public void fill_circle(int x, int y, int radius, int rgb) {
        Color color = new Color(rgb);
        commands.add(g -> {
            g.setColor(color);
            g.fillOval(x - radius, y - radius, radius * 2, radius * 2);
        });
    }

    /**
     * Set font: g:font("Arial", "bold", 14)
     * Style: "plain", "bold", "italic", "bold_italic"
     */
    public void font(String family, String style, int size) {
        int fontStyle = switch (style.toLowerCase()) {
            case "bold" -> Font.BOLD;
            case "italic" -> Font.ITALIC;
            case "bold_italic" -> Font.BOLD | Font.ITALIC;
            default -> Font.PLAIN;
        };
        Font f = new Font(family, fontStyle, size);
        commands.add(g -> g.setFont(f));
    }

    public void font(String family, int size) {
        font(family, "plain", size);
    }

    public void clear() {
        commands.clear();
    }

    /**
     * Execute all queued draw commands and clear the queue.
     * Called by ScriptOverlay during render.
     */
    public void flush(Graphics2D g) {
        for (Consumer<Graphics2D> cmd : commands) {
            cmd.accept(g);
        }
        commands.clear();
    }
}
