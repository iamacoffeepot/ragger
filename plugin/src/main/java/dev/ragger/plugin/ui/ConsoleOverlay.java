package dev.ragger.plugin.ui;

import net.runelite.api.Client;
import net.runelite.client.ui.overlay.Overlay;
import net.runelite.client.ui.overlay.OverlayLayer;
import net.runelite.client.ui.overlay.OverlayPosition;

import java.awt.*;
import java.awt.event.KeyEvent;
import java.util.ArrayList;
import java.util.List;
import java.util.function.Consumer;

/**
 * Full-screen console overlay toggled with F12.
 * Renders a semi-transparent terminal over the game canvas.
 */
public class ConsoleOverlay extends Overlay {

    private static final Color BG_COLOR = new Color(0x18, 0x18, 0x1E, 0xE8);
    private static final Color TEXT_COLOR = new Color(0xE0, 0xE0, 0xE0);
    private static final Color SENDER_COLOR = new Color(0xFF, 0xB3, 0x47);
    private static final Color TOOL_COLOR = new Color(0x99, 0x99, 0x99);
    private static final Color CODE_COLOR = new Color(0xA8, 0xD8, 0xF0);
    private static final Color CODE_BG = new Color(0x2A, 0x2A, 0x35, 0xCC);
    private static final Color QUOTE_COLOR = new Color(0xAA, 0xAA, 0xAA);
    private static final Color QUOTE_BAR = new Color(0x55, 0x55, 0x66);
    private static final Color LIST_BULLET_COLOR = new Color(0xFF, 0xB3, 0x47);
    private static final Color TABLE_HEADER_BG = new Color(0x2A, 0x2A, 0x38, 0xCC);
    private static final Color TABLE_BORDER = new Color(0x44, 0x44, 0x55);
    private static final Color INPUT_BG = new Color(0x22, 0x22, 0x2A, 0xEE);
    private static final Color INPUT_BORDER = new Color(0x55, 0x55, 0x66);
    private static final Color CURSOR_COLOR = new Color(0xFF, 0xB3, 0x47);
    private static final String FONT_FAMILY = "Menlo";
    private static final Font FONT = new Font(FONT_FAMILY, Font.PLAIN, 12);
    private static final Font FONT_BOLD = new Font(FONT_FAMILY, Font.BOLD, 12);
    private static final Font FONT_ITALIC = new Font(FONT_FAMILY, Font.ITALIC, 12);
    private static final Font FONT_BOLD_ITALIC = new Font(FONT_FAMILY, Font.BOLD | Font.ITALIC, 12);
    private static final Font FONT_HEADER = new Font(FONT_FAMILY, Font.BOLD, 14);
    private static final int PADDING = 12;
    private static final int LINE_HEIGHT = 16;

    private final Client client;
    private final Consumer<String> onMessage;
    private final List<ConsoleLine> lines = new ArrayList<>();
    private StringBuilder inputBuffer = new StringBuilder();
    private int cursorPos = 0;
    private boolean visible = false;
    private int scrollOffset = 0;
    private boolean cursorBlink = true;
    private long lastBlink = 0;

    public ConsoleOverlay(Client client, Consumer<String> onMessage) {
        this.client = client;
        this.onMessage = onMessage;
        setPosition(OverlayPosition.DYNAMIC);
        setLayer(OverlayLayer.ALWAYS_ON_TOP);
    }

    public boolean isVisible() {
        return visible;
    }

    public void toggle() {
        visible = !visible;
        scrollOffset = 0;
    }

    public void addMessage(String sender, String message) {
        lines.add(new ConsoleLine(sender, LineType.SENDER));

        message = message.strip();

        boolean inCodeBlock = false;
        boolean seenTableHeader = false;
        for (String rawLine : message.split("\n")) {
            if (rawLine.startsWith("```")) {
                inCodeBlock = !inCodeBlock;
                seenTableHeader = false;
                continue;
            }
            if (inCodeBlock) {
                lines.add(new ConsoleLine(rawLine, LineType.CODE));
                seenTableHeader = false;
            } else if (isListItem(rawLine)) {
                int indent = countIndent(rawLine);
                String stripped = rawLine.stripLeading();
                String bullet;
                String text;
                if (stripped.matches("^\\d+\\.\\s.*")) {
                    int dotIdx = stripped.indexOf('.');
                    bullet = stripped.substring(0, dotIdx + 1);
                    text = stripped.substring(dotIdx + 1).strip();
                } else {
                    bullet = "\u2022"; // •
                    text = stripped.substring(2); // skip "- " or "* "
                }
                lines.add(new ConsoleLine(text, LineType.LIST_ITEM, null, indent, bullet));
                seenTableHeader = false;
            } else if (rawLine.startsWith("    ")) {
                lines.add(new ConsoleLine(rawLine, LineType.CODE));
                seenTableHeader = false;
            } else if (rawLine.startsWith("> ")) {
                lines.add(new ConsoleLine(rawLine.substring(2), LineType.QUOTE));
                seenTableHeader = false;
            } else if (rawLine.startsWith(">")) {
                lines.add(new ConsoleLine(rawLine.substring(1), LineType.QUOTE));
                seenTableHeader = false;
            } else if (rawLine.contains("|") && rawLine.strip().startsWith("|")) {
                String trimmed = rawLine.strip();
                if (trimmed.matches("\\|[\\s\\-:|]+\\|")) {
                    continue; // skip separator row
                }
                String[] cells = parseCells(trimmed);
                if (!seenTableHeader) {
                    lines.add(new ConsoleLine(rawLine, LineType.TABLE_HEADER, cells));
                    seenTableHeader = true;
                } else {
                    lines.add(new ConsoleLine(rawLine, LineType.TABLE_ROW, cells));
                }
            } else if (rawLine.strip().matches("^[-*_]{3,}$")) {
                lines.add(new ConsoleLine(null, LineType.RULER));
                seenTableHeader = false;
            } else {
                seenTableHeader = false;
                lines.add(new ConsoleLine(rawLine, LineType.TEXT));
            }
        }
        scrollToBottom();
    }

    public void addToolMessage(String message) {
        lines.add(new ConsoleLine(message, LineType.TOOL));
        scrollToBottom();
    }

    public void addThinking() {
        lines.removeIf(l -> l.type == LineType.THINKING);
        lines.add(new ConsoleLine(null, LineType.THINKING));
    }

    public void removeThinking() {
        lines.removeIf(l -> l.type == LineType.THINKING);
    }

    public void clear() {
        lines.clear();
        scrollOffset = 0;
    }

    public void handleKeyTyped(KeyEvent e) {
        if (!visible) return;

        char c = e.getKeyChar();
        if (c == KeyEvent.VK_BACK_SPACE) {
            if (cursorPos > 0) {
                inputBuffer.deleteCharAt(cursorPos - 1);
                cursorPos--;
            }
        } else if (c == '\n' || c == '\r') {
            String text = inputBuffer.toString().trim();
            if (!text.isEmpty()) {
                inputBuffer.setLength(0);
                cursorPos = 0;
                onMessage.accept(text);
            }
        } else if (c != KeyEvent.CHAR_UNDEFINED && c >= 32) {
            inputBuffer.insert(cursorPos, c);
            cursorPos++;
        }

        e.consume();
    }

    public void handleKeyPressed(KeyEvent e) {
        if (!visible) return;

        // Paste support (Cmd+V / Ctrl+V)
        if (e.getKeyCode() == KeyEvent.VK_V && (e.isMetaDown() || e.isControlDown())) {
            try {
                String clip = (String) java.awt.Toolkit.getDefaultToolkit()
                    .getSystemClipboard()
                    .getData(java.awt.datatransfer.DataFlavor.stringFlavor);
                if (clip != null) {
                    String cleaned = clip.replaceAll("[\\r\\n]+", " ");
                    inputBuffer.insert(cursorPos, cleaned);
                    cursorPos += cleaned.length();
                }
            } catch (Exception ex) {
                // clipboard not available or wrong format
            }
            e.consume();
            return;
        }

        // Cursor movement
        if (e.getKeyCode() == KeyEvent.VK_LEFT) {
            if (cursorPos > 0) cursorPos--;
            e.consume();
        } else if (e.getKeyCode() == KeyEvent.VK_RIGHT) {
            if (cursorPos < inputBuffer.length()) cursorPos++;
            e.consume();
        } else if (e.getKeyCode() == KeyEvent.VK_HOME || (e.getKeyCode() == KeyEvent.VK_A && (e.isMetaDown() || e.isControlDown()))) {
            cursorPos = 0;
            e.consume();
        } else if (e.getKeyCode() == KeyEvent.VK_END || (e.getKeyCode() == KeyEvent.VK_E && (e.isMetaDown() || e.isControlDown()))) {
            cursorPos = inputBuffer.length();
            e.consume();
        } else if (e.getKeyCode() == KeyEvent.VK_DELETE) {
            if (cursorPos < inputBuffer.length()) {
                inputBuffer.deleteCharAt(cursorPos);
            }
            e.consume();
        } else if (e.getKeyCode() == KeyEvent.VK_ESCAPE) {
            visible = false;
            e.consume();
        }
    }

    public void handleScroll(int rotation) {
        if (!visible) return;
        scrollOffset = Math.max(0, Math.min(scrollOffset + rotation, Math.max(0, lines.size() - 1)));
    }


    private void scrollToBottom() {
        scrollOffset = 0;
    }

    @Override
    public Dimension render(Graphics2D g) {
        if (!visible) return null;

        int width = client.getCanvasWidth();
        int height = client.getCanvasHeight();
        int consoleHeight = height / 2;

        // Background
        g.setColor(BG_COLOR);
        g.fillRect(0, 0, width, consoleHeight);

        // Border at bottom
        g.setColor(INPUT_BORDER);
        g.drawLine(0, consoleHeight - 1, width, consoleHeight - 1);

        g.setFont(FONT);
        g.setRenderingHint(RenderingHints.KEY_TEXT_ANTIALIASING, RenderingHints.VALUE_TEXT_ANTIALIAS_ON);

        // Input area — wraps if text exceeds width
        g.setFont(FONT);
        FontMetrics fm = g.getFontMetrics();
        String inputText = inputBuffer.toString();
        int promptWidth = fm.stringWidth("\u25B6") + 8;
        int inputTextWidth = width - PADDING * 2 - promptWidth - 4;
        List<String> inputLines = wrapText(inputText.isEmpty() ? " " : inputText, fm, inputTextWidth);
        int inputLineCount = Math.max(1, inputLines.size());
        int inputAreaHeight = inputLineCount * LINE_HEIGHT + 4;
        int inputY = consoleHeight - inputAreaHeight - PADDING;

        g.setColor(INPUT_BG);
        g.fillRect(PADDING, inputY, width - PADDING * 2, inputAreaHeight);
        g.setColor(INPUT_BORDER);
        g.drawRect(PADDING, inputY, width - PADDING * 2, inputAreaHeight);

        // Prompt arrow
        g.setColor(SENDER_COLOR);
        g.drawString("\u25B6", PADDING + 4, inputY + LINE_HEIGHT - 2);

        // Input text lines
        g.setColor(TEXT_COLOR);
        int textX = PADDING + promptWidth;
        for (int il = 0; il < inputLines.size(); il++) {
            g.drawString(inputLines.get(il), textX, inputY + (il + 1) * LINE_HEIGHT - 2);
        }

        // Blinking cursor at cursorPos
        long now = System.currentTimeMillis();
        if (now - lastBlink > 500) {
            cursorBlink = !cursorBlink;
            lastBlink = now;
        }
        if (cursorBlink) {
            // Find which wrapped line the cursor is on
            String beforeCursor = inputText.substring(0, cursorPos);
            List<String> cursorLines = wrapText(beforeCursor.isEmpty() ? " " : beforeCursor, fm, inputTextWidth);
            int cursorLine = cursorLines.size() - 1;
            String lastCursorLine = cursorLines.get(cursorLine);
            int cursorX = textX + fm.stringWidth(lastCursorLine.equals(" ") ? "" : lastCursorLine);
            int cursorDrawY = inputY + cursorLine * LINE_HEIGHT + 2;
            g.setColor(CURSOR_COLOR);
            g.fillRect(cursorX, cursorDrawY, 2, LINE_HEIGHT - 2);
        }

        // Chat lines — render bottom-up above input
        int maxWidth = width - PADDING * 2 - 8;
        int maxLines = (inputY - PADDING) / LINE_HEIGHT;
        int startLine = Math.max(0, lines.size() - maxLines - scrollOffset);
        int endLine = Math.max(0, lines.size() - scrollOffset);
        int y = inputY - PADDING;

        for (int i = endLine - 1; i >= startLine && y > PADDING; i--) {
            ConsoleLine line = lines.get(i);

            switch (line.type) {
                case SENDER -> {
                    g.setFont(FONT_BOLD);
                    g.setColor(SENDER_COLOR);
                    g.drawString(line.text, PADDING + 4, y);
                    y -= LINE_HEIGHT;
                }
                case TEXT -> {
                    String text = line.text;
                    if (text.startsWith("# ") || text.startsWith("## ") || text.startsWith("### ")) {
                        text = text.replaceFirst("^#+\\s+", "");
                        g.setFont(FONT_HEADER);
                        g.setColor(TEXT_COLOR);
                        List<String> wrapped = wrapText(text, g.getFontMetrics(), maxWidth);
                        for (int w = wrapped.size() - 1; w >= 0 && y > PADDING; w--) {
                            g.drawString(wrapped.get(w), PADDING + 4, y);
                            y -= LINE_HEIGHT + 2;
                        }
                    } else {
                        g.setFont(FONT);
                        List<String> wrapped = wrapText(text, g.getFontMetrics(), maxWidth);
                        for (int w = wrapped.size() - 1; w >= 0 && y > PADDING; w--) {
                            drawStyledLine(g, wrapped.get(w), PADDING + 4, y, maxWidth);
                            y -= LINE_HEIGHT;
                        }
                    }
                }
                case CODE -> {
                    g.setFont(FONT);
                    String codeText = line.text;
                    // Truncate if too long, don't wrap code
                    if (g.getFontMetrics().stringWidth(codeText) > maxWidth) {
                        while (codeText.length() > 1 && g.getFontMetrics().stringWidth(codeText + "...") > maxWidth) {
                            codeText = codeText.substring(0, codeText.length() - 1);
                        }
                        codeText = codeText + "...";
                    }
                    g.setColor(CODE_BG);
                    g.fillRect(PADDING + 2, y - LINE_HEIGHT + 4, maxWidth, LINE_HEIGHT);
                    g.setColor(CODE_COLOR);
                    g.drawString(codeText, PADDING + 8, y);
                    y -= LINE_HEIGHT;
                }
                case LIST_ITEM -> {
                    int indentPx = PADDING + 4 + line.indent * 16;
                    g.setFont(FONT);
                    g.setColor(LIST_BULLET_COLOR);
                    g.drawString(line.bullet, indentPx, y);
                    int bulletWidth = g.getFontMetrics().stringWidth(line.bullet) + 6;
                    g.setColor(TEXT_COLOR);
                    List<String> wrapped = wrapText(line.text, g.getFontMetrics(), maxWidth - indentPx - bulletWidth + PADDING);
                    for (int w = wrapped.size() - 1; w >= 0 && y > PADDING; w--) {
                        if (w < wrapped.size() - 1) {
                            // continuation lines align after bullet
                            g.drawString(wrapped.get(w), indentPx + bulletWidth, y);
                        } else {
                            g.drawString(wrapped.get(w), indentPx + bulletWidth, y);
                        }
                        y -= LINE_HEIGHT;
                    }
                }
                case TABLE_HEADER -> {
                    drawTableRow(g, line.cells, PADDING + 4, y, maxWidth, true);
                    y -= LINE_HEIGHT;
                }
                case TABLE_ROW -> {
                    drawTableRow(g, line.cells, PADDING + 4, y, maxWidth, false);
                    y -= LINE_HEIGHT;
                }
                case QUOTE -> {
                    g.setFont(FONT_ITALIC);
                    List<String> wrapped = wrapText(line.text, g.getFontMetrics(), maxWidth - 12);
                    for (int w = wrapped.size() - 1; w >= 0 && y > PADDING; w--) {
                        g.setColor(QUOTE_BAR);
                        g.fillRect(PADDING + 4, y - LINE_HEIGHT + 4, 2, LINE_HEIGHT);
                        g.setColor(QUOTE_COLOR);
                        g.drawString(wrapped.get(w), PADDING + 12, y);
                        y -= LINE_HEIGHT;
                    }
                }
                case RULER -> {
                    g.setColor(TABLE_BORDER);
                    int rulerY = y - LINE_HEIGHT / 2 + 4;
                    g.drawLine(PADDING + 4, rulerY, PADDING + 4 + maxWidth, rulerY);
                    y -= LINE_HEIGHT;
                }
                case TOOL -> {
                    g.setFont(FONT);
                    List<String> wrapped = wrapText(line.text, g.getFontMetrics(), maxWidth);
                    for (int w = wrapped.size() - 1; w >= 0 && y > PADDING; w--) {
                        g.setColor(TOOL_COLOR);
                        g.drawString(wrapped.get(w), PADDING + 4, y);
                        y -= LINE_HEIGHT;
                    }
                }
                case THINKING -> {
                    g.setFont(FONT);
                    g.setColor(TOOL_COLOR);
                    int dots = (int) ((System.currentTimeMillis() / 400) % 3) + 1;
                    g.drawString("Thinking" + ".".repeat(dots), PADDING + 4, y);
                    y -= LINE_HEIGHT;
                }
            }
        }

        return new Dimension(width, consoleHeight);
    }

    /**
     * Draw a line with inline markdown: **bold**, *italic*, `code`
     */
    private void drawStyledLine(Graphics2D g, String text, int x, int y, int maxWidth) {
        int cx = x;
        int idx = 0;

        while (idx < text.length()) {
            // Inline code: `text`
            if (text.charAt(idx) == '`') {
                int end = text.indexOf('`', idx + 1);
                if (end > idx) {
                    String code = text.substring(idx + 1, end);
                    g.setFont(FONT);
                    int codeWidth = g.getFontMetrics().stringWidth(code) + 6;
                    g.setColor(CODE_BG);
                    g.fillRoundRect(cx, y - LINE_HEIGHT + 4, codeWidth, LINE_HEIGHT, 4, 4);
                    g.setColor(CODE_COLOR);
                    g.drawString(code, cx + 3, y);
                    cx += codeWidth + 1;
                    idx = end + 1;
                    continue;
                }
            }

            // Bold: **text**
            if (idx + 1 < text.length() && text.charAt(idx) == '*' && text.charAt(idx + 1) == '*') {
                int end = text.indexOf("**", idx + 2);
                if (end > idx) {
                    String bold = text.substring(idx + 2, end);
                    g.setFont(FONT_BOLD);
                    g.setColor(TEXT_COLOR);
                    g.drawString(bold, cx, y);
                    cx += g.getFontMetrics().stringWidth(bold);
                    idx = end + 2;
                    continue;
                }
            }

            // Italic: *text*
            if (text.charAt(idx) == '*') {
                int end = text.indexOf('*', idx + 1);
                if (end > idx) {
                    String italic = text.substring(idx + 1, end);
                    g.setFont(FONT_ITALIC);
                    g.setColor(TEXT_COLOR);
                    g.drawString(italic, cx, y);
                    cx += g.getFontMetrics().stringWidth(italic);
                    idx = end + 1;
                    continue;
                }
            }

            // Plain text — collect until next markdown marker
            int next = text.length();
            for (int j = idx + 1; j < text.length(); j++) {
                char c = text.charAt(j);
                if (c == '`' || c == '*') {
                    next = j;
                    break;
                }
            }

            String plain = text.substring(idx, next);
            g.setFont(FONT);
            g.setColor(TEXT_COLOR);
            g.drawString(plain, cx, y);
            cx += g.getFontMetrics().stringWidth(plain);
            idx = next;
        }
    }

    private static boolean isListItem(String line) {
        String stripped = line.stripLeading();
        return stripped.startsWith("- ") || stripped.startsWith("* ") || stripped.matches("^\\d+\\.\\s.*");
    }

    private static int countIndent(String line) {
        int spaces = 0;
        for (char c : line.toCharArray()) {
            if (c == ' ') spaces++;
            else break;
        }
        return spaces / 2; // 2 spaces per indent level
    }

    private static String[] parseCells(String row) {
        // Strip leading/trailing pipes and split
        if (row.startsWith("|")) row = row.substring(1);
        if (row.endsWith("|")) row = row.substring(0, row.length() - 1);
        String[] cells = row.split("\\|");
        for (int i = 0; i < cells.length; i++) {
            cells[i] = cells[i].strip();
        }
        return cells;
    }

    private void drawTableRow(Graphics2D g, String[] cells, int x, int y, int maxWidth, boolean isHeader) {
        if (cells == null || cells.length == 0) return;

        int cellWidth = Math.min(maxWidth / cells.length, 200);
        int cellPadding = 6;

        if (isHeader) {
            g.setColor(TABLE_HEADER_BG);
            g.fillRect(x, y - LINE_HEIGHT + 4, cellWidth * cells.length, LINE_HEIGHT);
            g.setFont(FONT_BOLD);
        } else {
            g.setFont(FONT);
        }

        for (int c = 0; c < cells.length; c++) {
            int cellX = x + c * cellWidth;

            // Cell border
            g.setColor(TABLE_BORDER);
            g.drawRect(cellX, y - LINE_HEIGHT + 4, cellWidth, LINE_HEIGHT);

            // Cell text
            g.setColor(isHeader ? SENDER_COLOR : TEXT_COLOR);
            String cellText = cells[c];
            // Truncate if too wide
            FontMetrics fm = g.getFontMetrics();
            if (fm.stringWidth(cellText) > cellWidth - cellPadding * 2) {
                while (cellText.length() > 1 && fm.stringWidth(cellText + "..") > cellWidth - cellPadding * 2) {
                    cellText = cellText.substring(0, cellText.length() - 1);
                }
                cellText = cellText + "..";
            }
            g.drawString(cellText, cellX + cellPadding, y);
        }
    }

    private static List<String> wrapText(String text, FontMetrics fm, int maxWidth) {
        List<String> result = new ArrayList<>();
        if (text == null || text.isEmpty()) {
            result.add("");
            return result;
        }

        String[] words = text.split(" ");
        StringBuilder current = new StringBuilder();

        for (String word : words) {
            if (current.isEmpty()) {
                current.append(word);
            } else if (fm.stringWidth(current + " " + word) <= maxWidth) {
                current.append(" ").append(word);
            } else {
                result.add(current.toString());
                current = new StringBuilder(word);
            }
        }
        if (!current.isEmpty()) {
            result.add(current.toString());
        }
        return result;
    }

    private enum LineType { SENDER, TEXT, CODE, QUOTE, TABLE_ROW, TABLE_HEADER, LIST_ITEM, RULER, TOOL, THINKING }

    private record ConsoleLine(String text, LineType type, String[] cells, int indent, String bullet) {
        ConsoleLine(String text, LineType type) {
            this(text, type, null, 0, null);
        }

        ConsoleLine(String text, LineType type, String[] cells) {
            this(text, type, cells, 0, null);
        }
    }
}
