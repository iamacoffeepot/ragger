package dev.ragger.plugin.scripting;

import java.awt.AlphaComposite;
import java.awt.BasicStroke;
import java.awt.Color;
import java.awt.Composite;
import java.awt.Font;
import java.awt.FontMetrics;
import java.awt.GradientPaint;
import java.awt.Graphics2D;
import java.awt.Paint;
import java.awt.Polygon;
import java.awt.Rectangle;
import java.awt.RenderingHints;
import java.awt.Shape;
import java.awt.Stroke;
import java.awt.geom.AffineTransform;
import java.awt.geom.GeneralPath;
import java.awt.image.BufferedImage;
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Deque;
import java.util.List;
import java.util.Map;
import java.util.function.Consumer;

/**
 * Lua binding for drawing overlays on the game screen.
 * Exposed as the argument "g" to on_render in Lua actors.
 *
 * Draw commands are queued during on_render and executed by ActorOverlay.
 */
public class OverlayApi {

    private final List<Consumer<Graphics2D>> commands = new ArrayList<>();

    // Path builder state (accumulated at queue time, not render time)
    private GeneralPath currentPath = null;

    // ── Basic drawing ──────────────────────────────────────────────────

    public void text(final int x, final int y, final String text, final int rgb) {
        final Color color = toColor(rgb);
        commands.add(g -> {
            g.setColor(color);
            g.drawString(text, x, y);
        });
    }

    public void text(final int x, final int y, final String text) {
        text(x, y, text, 0xFFFFFF);
    }

    public void rect(final int x, final int y, final int width, final int height, final int rgb) {
        final Color color = toColor(rgb);
        commands.add(g -> {
            g.setColor(color);
            g.drawRect(x, y, width, height);
        });
    }

    public void fill_rect(final int x, final int y, final int width, final int height, final int rgb) {
        final Color color = toColor(rgb);
        commands.add(g -> {
            if (!(g.getPaint() instanceof GradientPaint)) {
                g.setColor(color);
            }
            g.fillRect(x, y, width, height);
        });
    }

    public void round_rect(final int x, final int y, final int width, final int height, final int arcw, final int arch, final int rgb) {
        final Color color = toColor(rgb);
        commands.add(g -> {
            g.setColor(color);
            g.drawRoundRect(x, y, width, height, arcw, arch);
        });
    }

    public void fill_round_rect(final int x, final int y, final int width, final int height, final int arcw, final int arch, final int rgb) {
        final Color color = toColor(rgb);
        commands.add(g -> {
            if (!(g.getPaint() instanceof GradientPaint)) {
                g.setColor(color);
            }
            g.fillRoundRect(x, y, width, height, arcw, arch);
        });
    }

    public void line(final int x1, final int y1, final int x2, final int y2, final int rgb) {
        final Color color = toColor(rgb);
        commands.add(g -> {
            g.setColor(color);
            g.drawLine(x1, y1, x2, y2);
        });
    }

    public void circle(final int x, final int y, final int radius, final int rgb) {
        final Color color = toColor(rgb);
        commands.add(g -> {
            g.setColor(color);
            g.drawOval(x - radius, y - radius, radius * 2, radius * 2);
        });
    }

    public void fill_circle(final int x, final int y, final int radius, final int rgb) {
        final Color color = toColor(rgb);
        commands.add(g -> {
            if (!(g.getPaint() instanceof GradientPaint)) {
                g.setColor(color);
            }
            g.fillOval(x - radius, y - radius, radius * 2, radius * 2);
        });
    }

    public void arc(final int x, final int y, final int radius, final int startAngle, final int arcAngle, final int rgb) {
        final Color color = toColor(rgb);
        commands.add(g -> {
            g.setColor(color);
            g.drawArc(x - radius, y - radius, radius * 2, radius * 2, startAngle, arcAngle);
        });
    }

    public void fill_arc(final int x, final int y, final int radius, final int startAngle, final int arcAngle, final int rgb) {
        final Color color = toColor(rgb);
        commands.add(g -> {
            if (!(g.getPaint() instanceof GradientPaint)) {
                g.setColor(color);
            }
            g.fillArc(x - radius, y - radius, radius * 2, radius * 2, startAngle, arcAngle);
        });
    }

    // ── Polygon ────────────────────────────────────────────────────────

    /**
     * Draw a polygon outline: g:polygon(points, color)
     * points is a List of Maps with "x" and "y" keys (matches coords:world_tile_poly output).
     */
    @SuppressWarnings("unchecked")
    public void polygon(final List<?> points, final int rgb) {
        final Polygon poly = toPolygon(points);
        if (poly == null) {
            return;
        }

        final Color color = toColor(rgb);
        commands.add(g -> {
            g.setColor(color);
            g.drawPolygon(poly);
        });
    }

    /**
     * Draw a filled polygon: g:fill_polygon(points, color)
     */
    @SuppressWarnings("unchecked")
    public void fill_polygon(final List<?> points, final int rgb) {
        final Polygon poly = toPolygon(points);
        if (poly == null) {
            return;
        }

        final Color color = toColor(rgb);
        commands.add(g -> {
            if (!(g.getPaint() instanceof GradientPaint)) {
                g.setColor(color);
            }
            g.fillPolygon(poly);
        });
    }

    // ── Font & text measurement ────────────────────────────────────────

    /**
     * Set font: g:font("Arial", "bold", 14)
     * Style: "plain", "bold", "italic", "bold_italic"
     */
    public void font(final String family, final String style, final int size) {
        final int fontStyle = switch (style.toLowerCase()) {
            case "bold" -> Font.BOLD;
            case "italic" -> Font.ITALIC;
            case "bold_italic" -> Font.BOLD | Font.ITALIC;
            default -> Font.PLAIN;
        };
        final Font f = new Font(family, fontStyle, size);
        measureFont = f;
        commands.add(g -> g.setFont(f));
    }

    public void font(final String family, final int size) {
        font(family, "plain", size);
    }

    /**
     * Returns the pixel width of the given string using the current font.
     * Must be called after font() in the same frame for accurate results.
     * Uses a shared scratch graphics context for measurement.
     */
    public int text_width(final String text) {
        return measureGraphics().getFontMetrics().stringWidth(text);
    }

    /**
     * Returns the line height (ascent + descent) of the current font.
     */
    public int text_height() {
        final FontMetrics fm = measureGraphics().getFontMetrics();
        return fm.getAscent() + fm.getDescent();
    }

    /**
     * Returns the ascent of the current font (pixels above baseline).
     */
    public int text_ascent() {
        return measureGraphics().getFontMetrics().getAscent();
    }

    // Scratch graphics for font measurement — lazily created, tracks current font
    private static Graphics2D measureG;
    private Font measureFont;

    private Graphics2D measureGraphics() {
        if (measureG == null) {
            measureG = new BufferedImage(1, 1, BufferedImage.TYPE_INT_ARGB).createGraphics();
        }

        if (measureFont != null) {
            measureG.setFont(measureFont);
        }

        return measureG;
    }

    // ── Stroke ─────────────────────────────────────────────────────────

    /**
     * Set stroke width: g:stroke_width(2)
     */
    public void stroke_width(final float width) {
        final BasicStroke stroke = new BasicStroke(width, BasicStroke.CAP_ROUND, BasicStroke.JOIN_ROUND);
        commands.add(g -> g.setStroke(stroke));
    }

    /**
     * Set stroke with full control: g:stroke(width, cap, join)
     * cap: "butt", "round", "square"
     * join: "miter", "round", "bevel"
     */
    public void stroke(final float width, final String cap, final String join) {
        final int capVal = switch (cap.toLowerCase()) {
            case "round" -> BasicStroke.CAP_ROUND;
            case "square" -> BasicStroke.CAP_SQUARE;
            default -> BasicStroke.CAP_BUTT;
        };
        final int joinVal = switch (join.toLowerCase()) {
            case "round" -> BasicStroke.JOIN_ROUND;
            case "bevel" -> BasicStroke.JOIN_BEVEL;
            default -> BasicStroke.JOIN_MITER;
        };
        final BasicStroke s = new BasicStroke(width, capVal, joinVal);
        commands.add(g -> g.setStroke(s));
    }

    /**
     * Set dashed stroke: g:stroke_dash(width, dash_length, gap_length)
     */
    public void stroke_dash(final float width, final float dash, final float gap) {
        final BasicStroke s = new BasicStroke(
            width, BasicStroke.CAP_BUTT, BasicStroke.JOIN_MITER,
            10.0f, new float[]{dash, gap}, 0.0f
        );
        commands.add(g -> g.setStroke(s));
    }

    // ── Alpha & compositing ────────────────────────────────────────────

    /**
     * Set global opacity: g:opacity(0.5) — affects all subsequent drawing.
     * 0.0 = fully transparent, 1.0 = fully opaque.
     */
    public void opacity(final float alpha) {
        final float clamped = Math.max(0f, Math.min(1f, alpha));
        final AlphaComposite ac = AlphaComposite.getInstance(AlphaComposite.SRC_OVER, clamped);
        commands.add(g -> g.setComposite(ac));
    }

    // ── Color (direct set without drawing) ─────────────────────────────

    /**
     * Set draw color directly: g:color(0xAARRGGBB) or g:color(0xRRGGBB)
     */
    public void color(final int argb) {
        final Color c = toColor(argb);
        commands.add(g -> g.setColor(c));
    }

    // ── Transforms ─────────────────────────────────────────────────────

    /**
     * Translate the coordinate system: g:translate(dx, dy)
     */
    public void translate(final double dx, final double dy) {
        commands.add(g -> g.translate(dx, dy));
    }

    /**
     * Rotate around a point: g:rotate(radians, cx, cy)
     */
    public void rotate(final double radians, final double cx, final double cy) {
        commands.add(g -> g.rotate(radians, cx, cy));
    }

    /**
     * Rotate around origin: g:rotate(radians)
     */
    public void rotate(final double radians) {
        commands.add(g -> g.rotate(radians));
    }

    /**
     * Scale the coordinate system: g:scale(sx, sy)
     */
    public void scale(final double sx, final double sy) {
        commands.add(g -> g.scale(sx, sy));
    }

    // ── State save/restore ─────────────────────────────────────────────

    /**
     * Save the current graphics state (transform, clip, color, font, stroke, composite).
     * Use g:restore() to pop back to this state.
     */
    public void save() {
        commands.add(g -> {
            @SuppressWarnings("unchecked")
            Deque<GraphicsState> stack = (Deque<GraphicsState>) g.getRenderingHint(STATE_STACK_KEY);
            if (stack == null) {
                stack = new ArrayDeque<>();
                g.setRenderingHint(STATE_STACK_KEY, stack);
            }
            stack.push(new GraphicsState(g));
        });
    }

    /**
     * Restore the most recently saved graphics state.
     */
    public void restore() {
        commands.add(g -> {
            @SuppressWarnings("unchecked")
            final Deque<GraphicsState> stack = (Deque<GraphicsState>) g.getRenderingHint(STATE_STACK_KEY);
            if (stack != null && !stack.isEmpty()) {
                stack.pop().apply(g);
            }
        });
    }

    // ── Clipping ───────────────────────────────────────────────────────

    /**
     * Set a rectangular clip region: g:clip(x, y, w, h)
     * Only pixels inside the clip are drawn. Use save/restore to undo.
     */
    public void clip(final int x, final int y, final int w, final int h) {
        final Rectangle r = new Rectangle(x, y, w, h);
        commands.add(g -> g.clipRect(r.x, r.y, r.width, r.height));
    }

    // ── Gradient ───────────────────────────────────────────────────────

    /**
     * Set a linear gradient paint: g:gradient(x1, y1, color1, x2, y2, color2)
     * Subsequent fill operations use this gradient instead of a solid color.
     */
    public void gradient(final float x1, final float y1, final int rgb1, final float x2, final float y2, final int rgb2) {
        final Color c1 = toColor(rgb1);
        final Color c2 = toColor(rgb2);
        final GradientPaint gp = new GradientPaint(x1, y1, c1, x2, y2, c2);
        commands.add(g -> g.setPaint(gp));
    }

    /**
     * Cyclic linear gradient: g:gradient_cyclic(x1, y1, color1, x2, y2, color2)
     */
    public void gradient_cyclic(final float x1, final float y1, final int rgb1, final float x2, final float y2, final int rgb2) {
        final Color c1 = toColor(rgb1);
        final Color c2 = toColor(rgb2);
        final GradientPaint gp = new GradientPaint(x1, y1, c1, x2, y2, c2, true);
        commands.add(g -> g.setPaint(gp));
    }

    // ── Path API ───────────────────────────────────────────────────────

    /**
     * Begin a new path: g:begin_path()
     */
    public void begin_path() {
        currentPath = new GeneralPath();
    }

    /**
     * Move the path cursor without drawing: g:move_to(x, y)
     */
    public void move_to(final float x, final float y) {
        if (currentPath != null) {
            currentPath.moveTo(x, y);
        }
    }

    /**
     * Draw a straight line from current point: g:line_to(x, y)
     */
    public void line_to(final float x, final float y) {
        if (currentPath != null) {
            currentPath.lineTo(x, y);
        }
    }

    /**
     * Draw a quadratic bezier curve: g:quad_to(cx, cy, x, y)
     * (cx, cy) is the control point, (x, y) is the end point.
     */
    public void quad_to(final float cx, final float cy, final float x, final float y) {
        if (currentPath != null) {
            currentPath.quadTo(cx, cy, x, y);
        }
    }

    /**
     * Draw a cubic bezier curve: g:curve_to(cx1, cy1, cx2, cy2, x, y)
     */
    public void curve_to(final float cx1, final float cy1, final float cx2, final float cy2, final float x, final float y) {
        if (currentPath != null) {
            currentPath.curveTo(cx1, cy1, cx2, cy2, x, y);
        }
    }

    /**
     * Close the current path (line back to start): g:close_path()
     */
    public void close_path() {
        if (currentPath != null) {
            currentPath.closePath();
        }
    }

    /**
     * Stroke the current path outline: g:stroke_path(color)
     */
    public void stroke_path(final int rgb) {
        if (currentPath == null) {
            return;
        }

        final GeneralPath path = currentPath;
        final Color color = toColor(rgb);
        commands.add(g -> {
            g.setColor(color);
            g.draw(path);
        });
    }

    /**
     * Fill the current path: g:fill_path(color)
     */
    public void fill_path(final int rgb) {
        if (currentPath == null) {
            return;
        }

        final GeneralPath path = currentPath;
        final Color color = toColor(rgb);
        commands.add(g -> {
            if (!(g.getPaint() instanceof GradientPaint)) {
                g.setColor(color);
            }
            g.fill(path);
        });
    }

    // ── Rendering hints ────────────────────────────────────────────────

    /**
     * Enable or disable anti-aliasing: g:anti_alias(true)
     */
    public void anti_alias(final boolean enabled) {
        final Object val = enabled ? RenderingHints.VALUE_ANTIALIAS_ON : RenderingHints.VALUE_ANTIALIAS_OFF;
        commands.add(g -> g.setRenderingHint(RenderingHints.KEY_ANTIALIASING, val));
    }

    // ── Internals ──────────────────────────────────────────────────────

    /**
     * Convert an integer color to a Color object.
     * If the top 8 bits are nonzero, treat as ARGB (alpha in top byte).
     * Otherwise treat as opaque RGB (0x000000 = solid black, 0xFF0000 = red, etc.).
     */
    private static Color toColor(final int value) {
        final boolean hasAlpha = (value & 0xFF000000) != 0;
        return new Color(value, hasAlpha);
    }

    @SuppressWarnings("unchecked")
    private static Polygon toPolygon(final List<?> points) {
        if (points == null || points.isEmpty()) {
            return null;
        }

        final int n = points.size();
        final int[] xp = new int[n];
        final int[] yp = new int[n];

        for (int i = 0; i < n; i++) {
            final var pt = (Map<String, Object>) points.get(i);
            xp[i] = ((Number) pt.get("x")).intValue();
            yp[i] = ((Number) pt.get("y")).intValue();
        }

        return new Polygon(xp, yp, n);
    }

    // Custom rendering hint key for save/restore state stack
    private static final RenderingHints.Key STATE_STACK_KEY = new RenderingHints.Key(0x52_41_47) {
        @Override
        public boolean isCompatibleValue(final Object val) {
            return val instanceof Deque;
        }
    };

    /**
     * Snapshot of Graphics2D state for save/restore.
     */
    private record GraphicsState(
            AffineTransform transform,
            Shape clip,
            Color color,
            Font font,
            Stroke stroke,
            Composite composite,
            Paint paint
    ) {
        GraphicsState(final Graphics2D g) {
            this(
                    g.getTransform(),
                    g.getClip(),
                    g.getColor(),
                    g.getFont(),
                    g.getStroke(),
                    g.getComposite(),
                    g.getPaint()
            );
        }

        void apply(final Graphics2D g) {
            g.setTransform(transform);
            g.setClip(clip);
            g.setColor(color);
            g.setFont(font);
            g.setStroke(stroke);
            g.setComposite(composite);
            g.setPaint(paint);
        }
    }

    public void clear() {
        commands.clear();
        currentPath = null;
    }

    /**
     * Execute all queued draw commands and clear the queue.
     * Called by ActorOverlay during render.
     */
    public void flush(final Graphics2D g) {
        for (final Consumer<Graphics2D> cmd : commands) {
            cmd.accept(g);
        }

        commands.clear();
        currentPath = null;
    }
}
