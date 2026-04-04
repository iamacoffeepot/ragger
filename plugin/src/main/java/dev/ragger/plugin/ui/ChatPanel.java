package dev.ragger.plugin.ui;

import dev.ragger.plugin.scripting.ScriptManager;
import net.runelite.client.ui.PluginPanel;

import javax.swing.*;
import javax.swing.border.EmptyBorder;
import java.awt.*;
import java.awt.datatransfer.StringSelection;
import java.util.*;
import java.util.List;

/**
 * Sidebar panel with tabs for Scripts (tree view) and Templates.
 * Uses HTML rendering with the shared Ragger theme.
 */
public class ChatPanel extends PluginPanel {

    private static final String HINT_TAB = "Console";
    private static final String SCRIPTS_TAB = "Scripts";
    private static final String TEMPLATES_TAB = "Templates";

    private final JTabbedPane tabbedPane;
    private final JEditorPane hintPane;
    private final JEditorPane scriptsPane;
    private final JEditorPane templatesPane;

    private ScriptManager scriptManager;

    public ChatPanel() {
        super(false);
        setLayout(new BorderLayout());
        setBackground(RaggerTheme.BG);

        tabbedPane = new JTabbedPane(JTabbedPane.TOP);
        styleTabPane(tabbedPane);

        // ── Console hint tab ────────────────────────────────────────────
        hintPane = createHtmlPane();
        hintPane.setText(html("<div style='text-align:center; padding:20px;'>"
            + "<span style='color:" + RaggerTheme.hex(RaggerTheme.TEXT_DIMMER) + ";'>"
            + "Press <code>`</code> to open console</span></div>"));
        tabbedPane.addTab(HINT_TAB, wrap(hintPane));

        // ── Scripts tab ─────────────────────────────────────────────────
        scriptsPane = createHtmlPane();
        scriptsPane.setText(emptyState("No active scripts."));
        tabbedPane.addTab(SCRIPTS_TAB, wrap(scriptsPane));

        // ── Templates tab ───────────────────────────────────────────────
        templatesPane = createHtmlPane();
        templatesPane.setText(emptyState("No templates registered."));
        tabbedPane.addTab(TEMPLATES_TAB, wrap(templatesPane));

        add(tabbedPane, BorderLayout.CENTER);
    }

    /**
     * Bind to the script manager and start listening for changes.
     */
    public void setScriptManager(ScriptManager manager) {
        this.scriptManager = manager;
        manager.addChangeListener(() -> SwingUtilities.invokeLater(this::refresh));
        refresh();
    }

    /**
     * Rebuild both tabs from current ScriptManager state.
     */
    private void refresh() {
        if (scriptManager == null) return;
        refreshScripts();
        refreshTemplates();
    }

    // ── Scripts tab rendering ───────────────────────────────────────────

    private void refreshScripts() {
        List<String> names = scriptManager.list();
        if (names.isEmpty()) {
            scriptsPane.setText(emptyState("No active scripts."));
            return;
        }

        // Build tree structure
        TreeNode root = new TreeNode("");
        for (String name : names) {
            String[] parts = name.split("/");
            TreeNode node = root;
            for (String part : parts) {
                node = node.children.computeIfAbsent(part, TreeNode::new);
            }
            node.fullName = name;
        }

        StringBuilder sb = new StringBuilder();
        sb.append("<div style='padding:4px 0;'>");
        for (TreeNode child : root.children.values()) {
            renderTree(sb, child, 0);
        }
        sb.append("</div>");
        scriptsPane.setText(html(sb.toString()));
    }

    private void renderTree(StringBuilder sb, TreeNode node, int depth) {
        int indent = depth * 16;
        String bullet = node.children.isEmpty() ? "&#9656;" : "&#9662;"; // ▸ or ▾
        String nameColor = depth == 0
            ? RaggerTheme.hex(RaggerTheme.ACCENT)
            : RaggerTheme.hex(RaggerTheme.TEXT);
        String dimColor = RaggerTheme.hex(RaggerTheme.TEXT_DIM);

        sb.append("<div style='padding:3px 0 3px ").append(indent).append("px;'>");
        sb.append("<span style='color:").append(dimColor).append(";'>").append(bullet).append(" </span>");
        sb.append("<span style='color:").append(nameColor).append("; font-size:11px;'>").append(esc(node.name)).append("</span>");

        // Copy source link (only for leaf scripts that are actually loaded)
        if (node.fullName != null) {
            sb.append(" <a href='copy-source:").append(esc(node.fullName)).append("' style='color:")
              .append(RaggerTheme.hex(RaggerTheme.CODE)).append("; font-size:9px; text-decoration:none;'>[copy]</a>");
            sb.append(" <a href='stop-script:").append(esc(node.fullName)).append("' style='color:")
              .append(RaggerTheme.hex(RaggerTheme.TEXT_DIM)).append("; font-size:9px; text-decoration:none;'>[stop]</a>");
        }

        sb.append("</div>");

        for (TreeNode child : node.children.values()) {
            renderTree(sb, child, depth + 1);
        }
    }

    // ── Templates tab rendering ─────────────────────────────────────────

    private void refreshTemplates() {
        List<String> names = scriptManager.listTemplates();
        if (names.isEmpty()) {
            templatesPane.setText(emptyState("No templates registered."));
            return;
        }

        Collections.sort(names);
        StringBuilder sb = new StringBuilder();
        sb.append("<div style='padding:4px 0;'>");
        String accentHex = RaggerTheme.hex(RaggerTheme.ACCENT);
        String linkHex = RaggerTheme.hex(RaggerTheme.CODE);

        for (String name : names) {
            sb.append("<div style='padding:3px 0;'>");
            sb.append("<span style='color:").append(accentHex).append(";'>&#9670; </span>");
            sb.append("<span style='color:").append(RaggerTheme.hex(RaggerTheme.TEXT)).append(";'>")
              .append(esc(name)).append("</span>");
            sb.append(" <a href='copy-template:").append(esc(name)).append("' style='color:")
              .append(linkHex).append("; font-size:9px; text-decoration:none;'>[copy]</a>");
            sb.append("</div>");
        }
        sb.append("</div>");
        templatesPane.setText(html(sb.toString()));
    }

    // ── HTML helpers ────────────────────────────────────────────────────

    private JEditorPane createHtmlPane() {
        JEditorPane pane = new JEditorPane();
        pane.setContentType("text/html");
        pane.setEditable(false);
        pane.setOpaque(false);
        pane.putClientProperty(JEditorPane.HONOR_DISPLAY_PROPERTIES, Boolean.TRUE);
        pane.setFont(RaggerTheme.FONT);
        pane.setForeground(RaggerTheme.TEXT);
        pane.setBorder(new EmptyBorder(4, 8, 4, 8));

        // Handle link clicks
        pane.addHyperlinkListener(e -> {
            if (e.getEventType() == javax.swing.event.HyperlinkEvent.EventType.ACTIVATED) {
                handleLink(e.getDescription());
            }
        });

        return pane;
    }

    private void handleLink(String href) {
        if (scriptManager == null) return;

        if (href.startsWith("copy-source:")) {
            String name = href.substring("copy-source:".length());
            String source = scriptManager.getSource(name);
            if (source != null) {
                copyToClipboard(source);
            }
        } else if (href.startsWith("copy-template:")) {
            String name = href.substring("copy-template:".length());
            String source = scriptManager.getTemplate(name);
            if (source != null) {
                copyToClipboard(source);
            }
        } else if (href.startsWith("stop-script:")) {
            String name = href.substring("stop-script:".length());
            scriptManager.unload(name);
        }
    }

    private static void copyToClipboard(String text) {
        Toolkit.getDefaultToolkit().getSystemClipboard()
            .setContents(new StringSelection(text), null);
    }

    private static JScrollPane wrap(JEditorPane pane) {
        JScrollPane scroll = new JScrollPane(pane);
        scroll.setBackground(RaggerTheme.BG);
        scroll.getViewport().setBackground(RaggerTheme.BG);
        scroll.setBorder(BorderFactory.createEmptyBorder());
        scroll.setHorizontalScrollBarPolicy(ScrollPaneConstants.HORIZONTAL_SCROLLBAR_NEVER);
        return scroll;
    }

    private static void styleTabPane(JTabbedPane tabs) {
        tabs.setBackground(RaggerTheme.BG);
        tabs.setForeground(RaggerTheme.TEXT);
        tabs.setFont(RaggerTheme.FONT_SMALL);
        tabs.setOpaque(true);
        tabs.setTabPlacement(JTabbedPane.TOP);

        UIManager.put("TabbedPane.selected", RaggerTheme.BG_RAISED);
        UIManager.put("TabbedPane.contentAreaColor", RaggerTheme.BG);
        UIManager.put("TabbedPane.shadow", RaggerTheme.BORDER);
        UIManager.put("TabbedPane.darkShadow", RaggerTheme.BORDER);
    }

    private String html(String body) {
        String fontFamily = RaggerTheme.FONT.getFamily();
        return "<html><body style='"
            + "font-family:" + fontFamily + ",monospace;"
            + "font-size:12px;"
            + "color:" + RaggerTheme.hex(RaggerTheme.TEXT) + ";"
            + "background:" + RaggerTheme.hex(RaggerTheme.BG) + ";"
            + "margin:0; padding:0;"
            + "'>" + body + "</body></html>";
    }

    private static String emptyState(String message) {
        return "<html><body style='text-align:center; padding:20px; color:"
            + RaggerTheme.hex(RaggerTheme.TEXT_DIMMER) + ";'>"
            + message + "</body></html>";
    }

    private static String esc(String s) {
        return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("\"", "&quot;");
    }

    // ── Tree building ───────────────────────────────────────────────────

    private static class TreeNode {
        final String name;
        String fullName; // non-null only for nodes that are actual loaded scripts
        final LinkedHashMap<String, TreeNode> children = new LinkedHashMap<>();

        TreeNode(String name) {
            this.name = name;
        }
    }
}
