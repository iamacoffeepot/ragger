package dev.ragger.plugin.ui;

import net.runelite.api.Client;
import net.runelite.client.ui.overlay.Overlay;
import net.runelite.client.ui.overlay.OverlayLayer;
import net.runelite.client.ui.overlay.OverlayPosition;

import java.awt.Color;
import java.awt.Dimension;
import java.awt.Font;
import java.awt.FontMetrics;
import java.awt.Graphics2D;
import java.awt.RenderingHints;
import java.awt.Shape;
import java.awt.Toolkit;
import java.awt.datatransfer.DataFlavor;
import java.awt.event.KeyEvent;
import java.util.ArrayList;
import java.util.List;
import java.util.Set;
import java.util.function.Consumer;

/**
 * Full-screen console overlay toggled with F12.
 * Renders a semi-transparent terminal over the game canvas.
 */
public class ConsoleOverlay extends Overlay {

    // ── Theme aliases (delegate to RaggerTheme) ───────────────────────
    private static final Color BG_COLOR = RaggerTheme.BG_ALPHA;
    private static final Color TEXT_COLOR = RaggerTheme.TEXT;
    private static final Color SENDER_COLOR = RaggerTheme.ACCENT;
    private static final Color TOOL_COLOR = RaggerTheme.TEXT_DIM;
    private static final Color CODE_COLOR = RaggerTheme.CODE;
    private static final Color CODE_BG = RaggerTheme.BG_CODE;
    private static final Color SYN_KEYWORD = new Color(0xC5, 0x8B, 0xDB);   // purple
    private static final Color SYN_STRING = new Color(0x98, 0xC3, 0x79);    // green
    private static final Color SYN_NUMBER = new Color(0xD1, 0x9A, 0x66);    // orange
    private static final Color SYN_COMMENT = new Color(0x6A, 0x6A, 0x7A);   // dim gray
    private static final Set<String> KEYWORDS = Set.of(
        "if", "then", "else", "elseif", "end", "do", "while", "for", "in",
        "repeat", "until", "return", "local", "function", "not", "and", "or",
        "true", "false", "nil", "break", "goto",
        "def", "class", "import", "from", "pass", "raise", "try", "except",
        "finally", "with", "as", "yield", "lambda", "None", "True", "False",
        "self", "elif", "print", "is", "continue"
    );
    private static final Color QUOTE_COLOR = RaggerTheme.QUOTE;
    private static final Color QUOTE_BAR = RaggerTheme.BORDER;
    private static final Color LIST_BULLET_COLOR = RaggerTheme.ACCENT;
    private static final Color TABLE_HEADER_BG = RaggerTheme.BG_TABLE_HDR;
    private static final Color TABLE_BORDER = RaggerTheme.TABLE_BORDER;
    private static final Color INPUT_BG = RaggerTheme.INPUT_BG;
    private static final Color INPUT_BORDER = RaggerTheme.BORDER;
    private static final Color CURSOR_COLOR = RaggerTheme.ACCENT;
    private static final Font FONT = RaggerTheme.FONT;
    private static final Font FONT_BOLD = RaggerTheme.FONT_BOLD;
    private static final Font FONT_ITALIC = RaggerTheme.FONT_ITALIC;
    private static final Font FONT_BOLD_ITALIC = RaggerTheme.FONT_BOLD_ITALIC;
    private static final Font FONT_HEADER = RaggerTheme.FONT_HEADER;
    private static final int PADDING = 12;
    private static final int LINE_HEIGHT = 16;

    private final Client client;
    private final Consumer<String> onMessage;
    private final List<ConsoleLine> lines = new ArrayList<>();
    private final List<String> messageQueue = new ArrayList<>();
    private final StringBuilder inputBuffer = new StringBuilder();
    private int cursorPos = 0;
    private boolean visible = false;
    private boolean busy = false;
    private int scrollOffset = 0;
    private boolean cursorBlink = true;
    private long lastBlink = 0;
    private int streamStartIndex = -1;
    private StringBuilder streamBuffer;

    public ConsoleOverlay(final Client client, final Consumer<String> onMessage) {
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

    public void addMessage(final String sender, final String message) {
        lines.add(new ConsoleLine(sender, LineType.SENDER));
        parseMessageLines(message.strip());
        scrollToBottom();
    }

    private void parseMessageLines(final String message) {
        boolean inCodeBlock = false;
        boolean seenTableHeader = false;

        for (final String rawLine : message.split("\n")) {
            if (rawLine.startsWith("```")) {
                inCodeBlock = !inCodeBlock;
                seenTableHeader = false;
                continue;
            }

            if (inCodeBlock) {
                lines.add(new ConsoleLine(rawLine, LineType.CODE));
                seenTableHeader = false;
            } else if (isListItem(rawLine)) {
                final int indent = countIndent(rawLine);
                final String stripped = rawLine.stripLeading();
                final String bullet;
                final String text;

                if (stripped.matches("^\\d+\\.\\s.*")) {
                    final int dotIdx = stripped.indexOf('.');
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
                final String trimmed = rawLine.strip();
                final boolean isSeparator = trimmed.matches("\\|[\\s\\-:|]+\\|");

                if (isSeparator) {
                    continue;
                }

                final String[] cells = parseCells(trimmed);

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
    }

    /**
     * Begin a streaming message — shows the sender and prepares for text chunks.
     */
    public void beginStream(final String sender) {
        lines.add(new ConsoleLine(sender, LineType.SENDER));
        streamStartIndex = lines.size();
        streamBuffer = new StringBuilder();
        scrollToBottom();
    }

    /**
     * Continue streaming after a tool call — no sender header.
     */
    public void beginStreamContinuation() {
        streamStartIndex = lines.size();
        streamBuffer = new StringBuilder();
    }

    /**
     * Append a text chunk to the current streaming message.
     */
    public void appendStream(final String text) {
        if (streamBuffer == null) {
            return;
        }

        streamBuffer.append(text);

        // Re-parse the full buffer and replace lines from streamStartIndex
        while (lines.size() > streamStartIndex) {
            lines.remove(lines.size() - 1);
        }

        parseMessageLines(streamBuffer.toString().strip());
        scrollToBottom();
    }

    /**
     * End the streaming message.
     */
    public void endStream() {
        streamBuffer = null;
        streamStartIndex = -1;
    }

    public void addToolMessage(final String message) {
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

    public void setBusy(final boolean busy) {
        this.busy = busy;
    }

    /**
     * Remove and return the next queued message, or null if empty.
     */
    public String pollQueue() {
        if (messageQueue.isEmpty()) {
            return null;
        }
        return messageQueue.remove(0);
    }

    public void clearQueue() {
        messageQueue.clear();
    }

    public void handleKeyTyped(final KeyEvent e) {
        if (!visible) {
            return;
        }

        final char c = e.getKeyChar();

        if (c == KeyEvent.VK_BACK_SPACE) {
            if (cursorPos > 0) {
                inputBuffer.deleteCharAt(cursorPos - 1);
                cursorPos--;
            }
        } else if (c == '\n' || c == '\r') {
            final String text = inputBuffer.toString().trim();

            if (!text.isEmpty()) {
                inputBuffer.setLength(0);
                cursorPos = 0;

                if (busy && !text.startsWith("/")) {
                    messageQueue.add(text);
                } else {
                    onMessage.accept(text);
                }
            }
        } else if (c != KeyEvent.CHAR_UNDEFINED && c >= 32) {
            inputBuffer.insert(cursorPos, c);
            cursorPos++;
        }

        e.consume();
    }

    public void handleKeyPressed(final KeyEvent e) {
        if (!visible) {
            return;
        }

        final int keyCode = e.getKeyCode();
        final boolean hasModifier = e.isMetaDown() || e.isControlDown();

        // Paste support (Cmd+V / Ctrl+V)
        if (keyCode == KeyEvent.VK_V && hasModifier) {
            try {
                final String clip = (String) Toolkit.getDefaultToolkit()
                    .getSystemClipboard()
                    .getData(DataFlavor.stringFlavor);

                if (clip != null) {
                    final String cleaned = clip.replaceAll("[\\r\\n]+", " ");
                    inputBuffer.insert(cursorPos, cleaned);
                    cursorPos += cleaned.length();
                }
            } catch (final Exception ex) {
                // clipboard not available or wrong format
            }

            e.consume();
            return;
        }

        // Cursor movement
        if (keyCode == KeyEvent.VK_LEFT) {
            if (cursorPos > 0) {
                cursorPos--;
            }
            e.consume();
        } else if (keyCode == KeyEvent.VK_RIGHT) {
            if (cursorPos < inputBuffer.length()) {
                cursorPos++;
            }
            e.consume();
        } else if (keyCode == KeyEvent.VK_HOME || (keyCode == KeyEvent.VK_A && hasModifier)) {
            cursorPos = 0;
            e.consume();
        } else if (keyCode == KeyEvent.VK_END || (keyCode == KeyEvent.VK_E && hasModifier)) {
            cursorPos = inputBuffer.length();
            e.consume();
        } else if (keyCode == KeyEvent.VK_DELETE) {
            if (cursorPos < inputBuffer.length()) {
                inputBuffer.deleteCharAt(cursorPos);
            }
            e.consume();
        } else if (keyCode == KeyEvent.VK_ESCAPE) {
            visible = false;
            e.consume();
        }
    }

    public void handleScroll(final int rotation) {
        if (!visible) {
            return;
        }

        final int consoleHeight = client.getCanvasHeight() / 2;
        final int visibleLines = (consoleHeight - PADDING * 3 - LINE_HEIGHT) / LINE_HEIGHT;
        final int maxScroll = Math.max(0, lines.size() - visibleLines);
        scrollOffset = Math.max(0, Math.min(scrollOffset + rotation, maxScroll));
    }

    private void scrollToBottom() {
        scrollOffset = 0;
    }

    @Override
    public Dimension render(final Graphics2D g) {
        if (!visible) {
            return null;
        }

        final int width = client.getCanvasWidth();
        final int height = client.getCanvasHeight();
        final int consoleHeight = height / 2;

        // Background
        g.setColor(BG_COLOR);
        g.fillRect(0, 0, width, consoleHeight);

        // Border at bottom
        g.setColor(INPUT_BORDER);
        g.drawLine(0, consoleHeight - 1, width, consoleHeight - 1);

        g.setFont(FONT);
        g.setRenderingHint(RenderingHints.KEY_TEXT_ANTIALIASING, RenderingHints.VALUE_TEXT_ANTIALIAS_ON);

        // Input area
        g.setFont(FONT);
        final FontMetrics fm = g.getFontMetrics();
        final String inputText = inputBuffer.toString();
        final int inputInset = PADDING + 4;
        final int promptWidth = fm.stringWidth("\u276F") + 8;
        final int inputTextWidth = width - inputInset * 2 - promptWidth;

        // Character-accurate line wrapping for input
        final List<String> inputLines = new ArrayList<>();
        int lineStart = 0;

        while (lineStart < inputText.length()) {
            int lineEnd = lineStart;

            while (lineEnd < inputText.length()
                    && fm.stringWidth(inputText.substring(lineStart, lineEnd + 1)) <= inputTextWidth) {
                lineEnd++;
            }

            if (lineEnd == lineStart) {
                lineEnd = lineStart + 1;
            }

            inputLines.add(inputText.substring(lineStart, lineEnd));
            lineStart = lineEnd;
        }

        if (inputLines.isEmpty()) {
            inputLines.add("");
        }

        final int inputLineCount = Math.min(inputLines.size(), 16);
        final int inputAreaHeight = inputLineCount * LINE_HEIGHT + LINE_HEIGHT;
        final int queueHeight = messageQueue.size() * LINE_HEIGHT;
        final int inputY = consoleHeight - inputAreaHeight - queueHeight - PADDING;

        // Queued messages — rendered below input box in tool style
        if (!messageQueue.isEmpty()) {
            g.setFont(FONT);
            g.setColor(TOOL_COLOR);
            final int queueY = inputY + inputAreaHeight + LINE_HEIGHT;

            for (int qi = 0; qi < messageQueue.size(); qi++) {
                String qMsg = messageQueue.get(qi);
                final boolean tooWide = fm.stringWidth(qMsg) > inputTextWidth;

                if (tooWide) {
                    while (qMsg.length() > 1 && fm.stringWidth(qMsg + "...") > inputTextWidth) {
                        qMsg = qMsg.substring(0, qMsg.length() - 1);
                    }
                    qMsg = qMsg + "...";
                }

                g.drawString("\u25B8 " + qMsg, inputInset + 4, queueY + qi * LINE_HEIGHT);
            }
        }

        // Top line
        g.setColor(INPUT_BORDER);
        g.drawLine(inputInset, inputY, width - inputInset, inputY);

        // Bottom line
        g.drawLine(inputInset, inputY + inputAreaHeight, width - inputInset, inputY + inputAreaHeight);

        // Text vertically centered between the two lines
        final int baselineOffset = inputY + LINE_HEIGHT + (fm.getAscent() - fm.getDescent()) / 2;
        g.setColor(TOOL_COLOR);
        g.drawString("\u276F", inputInset + 4, baselineOffset);

        // Input text lines
        g.setColor(TEXT_COLOR);
        final int textX = inputInset + promptWidth;

        for (int il = 0; il < inputLines.size(); il++) {
            g.drawString(inputLines.get(il), textX, baselineOffset + il * LINE_HEIGHT);
        }

        // Cursor at cursorPos
        {
            int charsConsumed = 0;
            int cursorLine = 0;
            int cursorLineOffset = cursorPos;

            for (int il = 0; il < inputLines.size(); il++) {
                final int lineLen = inputLines.get(il).length();

                if (charsConsumed + lineLen >= cursorPos) {
                    cursorLine = il;
                    cursorLineOffset = cursorPos - charsConsumed;
                    break;
                }

                charsConsumed += lineLen;
            }

            final String lineText = inputLines.get(cursorLine);
            final int clampedOffset = Math.min(cursorLineOffset, lineText.length());
            final String beforeCursorOnLine = lineText.substring(0, clampedOffset);
            final int cursorX = textX + fm.stringWidth(beforeCursorOnLine);
            final int cursorDrawY = baselineOffset + cursorLine * LINE_HEIGHT - fm.getAscent();

            // Block cursor — covers the character cell
            final boolean atEndOfLine = cursorLineOffset >= lineText.length();
            final int charWidth = atEndOfLine
                ? fm.charWidth(' ')
                : fm.charWidth(lineText.charAt(cursorLineOffset));

            g.setColor(CURSOR_COLOR);
            g.fillRect(cursorX, cursorDrawY, charWidth, fm.getAscent() + fm.getDescent());

            // Draw the character under the cursor in the background color
            if (!atEndOfLine) {
                final String cursorChar = String.valueOf(lineText.charAt(cursorLineOffset));
                g.setColor(BG_COLOR);
                g.drawString(cursorChar, cursorX, baselineOffset + cursorLine * LINE_HEIGHT);
            }
        }

        // Chat lines — render bottom-up above input
        final int maxWidth = width - PADDING * 2 - 8;
        final int maxLines = (inputY - PADDING) / LINE_HEIGHT;
        final int startLine = Math.max(0, lines.size() - maxLines - scrollOffset);
        final int endLine = Math.max(0, lines.size() - scrollOffset);
        int y = inputY - PADDING;

        for (int i = endLine - 1; i >= startLine && y > PADDING; i--) {
            final ConsoleLine line = lines.get(i);

            switch (line.type) {
                case SENDER -> {
                    g.setFont(FONT_BOLD);
                    g.setColor(SENDER_COLOR);
                    g.drawString("\u2022 " + line.text, PADDING + 4, y);
                    y -= LINE_HEIGHT;
                }

                case TEXT -> {
                    final String text = line.text;
                    final boolean isHeader = text.startsWith("# ")
                        || text.startsWith("## ")
                        || text.startsWith("### ");

                    if (isHeader) {
                        final String headerText = text.replaceFirst("^#+\\s+", "");
                        g.setFont(FONT_HEADER);
                        g.setColor(TEXT_COLOR);
                        final List<String> wrapped = wrapText(headerText, g.getFontMetrics(), maxWidth);

                        for (int w = wrapped.size() - 1; w >= 0 && y > PADDING; w--) {
                            g.drawString(wrapped.get(w), PADDING + 4, y);
                            y -= LINE_HEIGHT + 2;
                        }
                    } else {
                        g.setFont(FONT);
                        final List<String> wrapped = wrapText(text, g.getFontMetrics(), maxWidth);

                        for (int w = wrapped.size() - 1; w >= 0 && y > PADDING; w--) {
                            drawStyledLine(g, wrapped.get(w), PADDING + 4, y, maxWidth);
                            y -= LINE_HEIGHT;
                        }
                    }
                }

                case CODE -> {
                    g.setFont(FONT);
                    String codeText = line.text;
                    final int codeWidth = g.getFontMetrics().stringWidth(codeText);
                    final boolean codeTooWide = codeWidth > maxWidth;

                    if (codeTooWide) {
                        while (codeText.length() > 1
                                && g.getFontMetrics().stringWidth(codeText + "...") > maxWidth) {
                            codeText = codeText.substring(0, codeText.length() - 1);
                        }
                        codeText = codeText + "...";
                    }

                    g.setColor(CODE_BG);
                    g.fillRect(PADDING + 2, y - LINE_HEIGHT + 4, maxWidth, LINE_HEIGHT);
                    drawSyntaxHighlighted(g, codeText, PADDING + 8, y);
                    y -= LINE_HEIGHT;
                }

                case LIST_ITEM -> {
                    final int indentPx = PADDING + 4 + line.indent * 16;
                    g.setFont(FONT);
                    final int bulletWidth = g.getFontMetrics().stringWidth(line.bullet) + 6;
                    final int listTextWidth = maxWidth - indentPx - bulletWidth + PADDING;
                    final List<String> wrapped = wrapText(line.text, g.getFontMetrics(), listTextWidth);

                    for (int w = wrapped.size() - 1; w >= 0 && y > PADDING; w--) {
                        drawStyledLine(g, wrapped.get(w), indentPx + bulletWidth, y, listTextWidth);
                        y -= LINE_HEIGHT;
                    }

                    // Draw bullet aligned with the first line (which is now at y + LINE_HEIGHT)
                    g.setColor(LIST_BULLET_COLOR);
                    g.drawString(line.bullet, indentPx, y + LINE_HEIGHT);
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
                    final List<String> wrapped = wrapText(line.text, g.getFontMetrics(), maxWidth - 12);

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
                    final int rulerY = y - LINE_HEIGHT / 2 + 4;
                    g.drawLine(PADDING + 4, rulerY, PADDING + 4 + maxWidth, rulerY);
                    y -= LINE_HEIGHT;
                }

                case TOOL -> {
                    g.setFont(FONT);
                    final List<String> wrapped = wrapText(line.text, g.getFontMetrics(), maxWidth);

                    for (int w = wrapped.size() - 1; w >= 0 && y > PADDING; w--) {
                        g.setColor(TOOL_COLOR);
                        g.drawString(wrapped.get(w), PADDING + 4, y);
                        y -= LINE_HEIGHT;
                    }
                }

                case THINKING -> {
                    g.setFont(FONT);
                    g.setColor(TOOL_COLOR);
                    final int dots = (int) ((System.currentTimeMillis() / 400) % 3) + 1;
                    g.drawString("Thinking" + ".".repeat(dots), PADDING + 4, y);
                    y -= LINE_HEIGHT;
                }
            }
        }

        return new Dimension(width, consoleHeight);
    }

    /**
     * Draw a line of code with syntax highlighting.
     * Tokenizes into keywords, strings, numbers, comments, and plain code.
     */
    private void drawSyntaxHighlighted(final Graphics2D g, final String text, final int x, final int y) {
        g.setFont(FONT);
        final FontMetrics fm = g.getFontMetrics();
        int cx = x;
        int idx = 0;

        while (idx < text.length()) {
            final char c = text.charAt(idx);

            // Comments: -- (Lua) or # (Python)
            final boolean isLuaComment = c == '-' && idx + 1 < text.length() && text.charAt(idx + 1) == '-';
            final boolean isPythonComment = c == '#';

            if (isLuaComment || isPythonComment) {
                g.setColor(SYN_COMMENT);
                g.drawString(text.substring(idx), cx, y);
                return;
            }

            // Strings: "..." or '...'
            if (c == '"' || c == '\'') {
                int end = text.indexOf(c, idx + 1);

                if (end < 0) {
                    end = text.length() - 1;
                }

                final String str = text.substring(idx, end + 1);
                g.setColor(SYN_STRING);
                g.drawString(str, cx, y);
                cx += fm.stringWidth(str);
                idx = end + 1;
                continue;
            }

            // Numbers
            final boolean isDigitStart = Character.isDigit(c);
            final boolean isDotDigit = c == '.' && idx + 1 < text.length()
                && Character.isDigit(text.charAt(idx + 1));

            if (isDigitStart || isDotDigit) {
                int end = idx;

                while (end < text.length()) {
                    final char ch = text.charAt(end);
                    final boolean isNumChar = Character.isDigit(ch) || ch == '.' || ch == 'x' || ch == 'X'
                        || (ch >= 'a' && ch <= 'f') || (ch >= 'A' && ch <= 'F');

                    if (!isNumChar) {
                        break;
                    }

                    end++;
                }

                final String num = text.substring(idx, end);
                g.setColor(SYN_NUMBER);
                g.drawString(num, cx, y);
                cx += fm.stringWidth(num);
                idx = end;
                continue;
            }

            // Words (potential keywords)
            if (Character.isLetter(c) || c == '_') {
                int end = idx;

                while (end < text.length() && (Character.isLetterOrDigit(text.charAt(end)) || text.charAt(end) == '_')) {
                    end++;
                }

                final String word = text.substring(idx, end);

                if (KEYWORDS.contains(word)) {
                    g.setColor(SYN_KEYWORD);
                    g.setFont(FONT_BOLD);
                    g.drawString(word, cx, y);
                    cx += g.getFontMetrics().stringWidth(word);
                    g.setFont(FONT);
                } else {
                    g.setColor(CODE_COLOR);
                    g.drawString(word, cx, y);
                    cx += fm.stringWidth(word);
                }

                idx = end;
                continue;
            }

            // Everything else (operators, punctuation, whitespace)
            g.setColor(CODE_COLOR);
            final String ch = String.valueOf(c);
            g.drawString(ch, cx, y);
            cx += fm.stringWidth(ch);
            idx++;
        }
    }

    private void drawStyledLine(
        final Graphics2D g,
        final String text,
        final int x,
        final int y,
        final int maxWidth
    ) {
        int cx = x;
        int idx = 0;

        while (idx < text.length()) {
            // Inline code: `text`
            if (text.charAt(idx) == '`') {
                final int end = text.indexOf('`', idx + 1);

                if (end > idx) {
                    final String code = text.substring(idx + 1, end);
                    g.setFont(FONT);
                    final int codeWidth = g.getFontMetrics().stringWidth(code) + 10;
                    g.setColor(CODE_BG);
                    g.fillRoundRect(cx, y - LINE_HEIGHT + 2, codeWidth, LINE_HEIGHT + 2, 4, 4);
                    g.setColor(CODE_COLOR);
                    g.drawString(code, cx + 5, y);
                    cx += codeWidth + 2;
                    idx = end + 1;
                    continue;
                }
            }

            // Bold: **text**
            final boolean isBoldMarker = idx + 1 < text.length()
                && text.charAt(idx) == '*'
                && text.charAt(idx + 1) == '*';

            if (isBoldMarker) {
                final int end = text.indexOf("**", idx + 2);

                if (end > idx) {
                    final String bold = text.substring(idx + 2, end);
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
                final int end = text.indexOf('*', idx + 1);

                if (end > idx) {
                    final String italic = text.substring(idx + 1, end);
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
                final char c = text.charAt(j);

                if (c == '`' || c == '*') {
                    next = j;
                    break;
                }
            }

            final String plain = text.substring(idx, next);
            g.setFont(FONT);
            g.setColor(TEXT_COLOR);
            g.drawString(plain, cx, y);
            cx += g.getFontMetrics().stringWidth(plain);
            idx = next;
        }
    }

    private static boolean isListItem(final String line) {
        final String stripped = line.stripLeading();
        return stripped.startsWith("- ") || stripped.startsWith("* ") || stripped.matches("^\\d+\\.\\s.*");
    }

    private static int countIndent(final String line) {
        int spaces = 0;

        for (final char c : line.toCharArray()) {
            if (c == ' ') {
                spaces++;
            } else {
                break;
            }
        }

        return spaces / 2; // 2 spaces per indent level
    }

    private static String[] parseCells(final String row) {
        String trimmed = row;

        if (trimmed.startsWith("|")) {
            trimmed = trimmed.substring(1);
        }

        if (trimmed.endsWith("|")) {
            trimmed = trimmed.substring(0, trimmed.length() - 1);
        }

        final String[] cells = trimmed.split("\\|");

        for (int i = 0; i < cells.length; i++) {
            cells[i] = cells[i].strip();
        }

        return cells;
    }

    private void drawTableRow(
        final Graphics2D g,
        final String[] cells,
        final int x,
        final int y,
        final int maxWidth,
        final boolean isHeader
    ) {
        if (cells == null || cells.length == 0) {
            return;
        }

        final int cellWidth = Math.min(maxWidth / cells.length, 200);
        final int cellPadding = 6;

        if (isHeader) {
            g.setColor(TABLE_HEADER_BG);
            g.fillRect(x, y - LINE_HEIGHT + 4, cellWidth * cells.length, LINE_HEIGHT);
            g.setFont(FONT_BOLD);
        } else {
            g.setFont(FONT);
        }

        for (int c = 0; c < cells.length; c++) {
            final int cellX = x + c * cellWidth;

            // Cell border
            g.setColor(TABLE_BORDER);
            g.drawRect(cellX, y - LINE_HEIGHT + 4, cellWidth, LINE_HEIGHT);

            // Cell text — clip to cell bounds and render with inline formatting
            g.setColor(isHeader ? SENDER_COLOR : TEXT_COLOR);
            final Shape oldClip = g.getClip();
            g.clipRect(cellX + cellPadding, y - LINE_HEIGHT + 4, cellWidth - cellPadding * 2, LINE_HEIGHT);

            if (isHeader) {
                g.setFont(FONT_BOLD);
                g.drawString(cells[c], cellX + cellPadding, y);
            } else {
                drawStyledLine(g, cells[c], cellX + cellPadding, y, cellWidth - cellPadding * 2);
            }

            g.setClip(oldClip);
        }
    }

    private static List<String> wrapText(final String text, final FontMetrics fm, final int maxWidth) {
        final List<String> result = new ArrayList<>();

        if (text == null || text.isEmpty()) {
            result.add("");
            return result;
        }

        final String[] words = text.split(" ");
        StringBuilder current = new StringBuilder();

        for (final String word : words) {
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

    private enum LineType {
        SENDER, TEXT, CODE, QUOTE, TABLE_ROW, TABLE_HEADER, LIST_ITEM, RULER, TOOL, THINKING
    }

    private record ConsoleLine(String text, LineType type, String[] cells, int indent, String bullet) {
        ConsoleLine(final String text, final LineType type) {
            this(text, type, null, 0, null);
        }

        ConsoleLine(final String text, final LineType type, final String[] cells) {
            this(text, type, cells, 0, null);
        }
    }
}
