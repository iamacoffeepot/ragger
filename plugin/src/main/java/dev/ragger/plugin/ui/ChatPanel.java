package dev.ragger.plugin.ui;

import dev.ragger.plugin.scripting.ActorManager;
import net.runelite.client.ui.PluginPanel;

import java.awt.BorderLayout;
import java.awt.Toolkit;
import java.awt.datatransfer.StringSelection;
import java.util.Collections;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Set;
import javax.swing.BorderFactory;
import javax.swing.JEditorPane;
import javax.swing.JScrollPane;
import javax.swing.JTabbedPane;
import javax.swing.ScrollPaneConstants;
import javax.swing.SwingUtilities;
import javax.swing.UIManager;
import javax.swing.border.EmptyBorder;
import javax.swing.event.HyperlinkEvent;
import javax.swing.text.DefaultCaret;

/**
 * Sidebar panel with tabs for Scripts (tree view) and Templates.
 * Uses HTML rendering with the shared Ragger theme.
 */
public class ChatPanel extends PluginPanel {

    private static final String HINT_TAB = "Console";
    private static final String ACTORS_TAB = "Actors";
    private static final String TEMPLATES_TAB = "Templates";

    private final JTabbedPane tabbedPane;
    private final JEditorPane hintPane;
    private final JEditorPane actorsPane;
    private final JEditorPane templatesPane;

    private ActorManager actorManager;
    private final Set<String> collapsed = new HashSet<>();

    public ChatPanel() {
        super(false);
        setLayout(new BorderLayout());
        setBackground(RaggerTheme.BG);

        tabbedPane = new JTabbedPane(JTabbedPane.TOP);
        tabbedPane.putClientProperty("JTabbedPane.tabAreaAlignment", "fill");
        styleTabPane(tabbedPane);

        // ── Console hint tab ────────────────────────────────────────────
        hintPane = createHtmlPane();
        hintPane.setText(html("<div style='text-align:center; padding:20px;'>"
            + "<span style='color:" + RaggerTheme.hex(RaggerTheme.TEXT_DIMMER) + ";'>"
            + "Press <code>`</code> to open console</span></div>"));
        tabbedPane.addTab(HINT_TAB, wrap(hintPane));

        // ── Scripts tab ─────────────────────────────────────────────────
        actorsPane = createHtmlPane();
        actorsPane.setText(emptyState("No active actors."));
        tabbedPane.addTab(ACTORS_TAB, wrap(actorsPane));

        // ── Templates tab ───────────────────────────────────────────────
        templatesPane = createHtmlPane();
        templatesPane.setText(emptyState("No templates registered."));
        tabbedPane.addTab(TEMPLATES_TAB, wrap(templatesPane));

        add(tabbedPane, BorderLayout.CENTER);
    }

    /**
     * Bind to the script manager and start listening for changes.
     */
    public void setActorManager(final ActorManager manager) {
        this.actorManager = manager;
        manager.addChangeListener(() -> SwingUtilities.invokeLater(this::refresh));
        refresh();
    }

    /**
     * Rebuild both tabs from current ActorManager state.
     */
    private void refresh() {
        if (actorManager == null) {
            return;
        }

        refreshActors();
        refreshTemplates();
    }

    // ── Actors tab rendering ───────────────────────────────────────────

    private void refreshActors() {
        final List<String> names = actorManager.list();

        if (names.isEmpty()) {
            actorsPane.setText(emptyState("No active actors."));
            return;
        }

        // Build tree structure
        final TreeNode root = new TreeNode("");
        for (final String name : names) {
            final String[] parts = name.split("/");
            TreeNode node = root;
            for (final String part : parts) {
                node = node.children.computeIfAbsent(part, TreeNode::new);
            }
            node.fullName = name;
        }

        final StringBuilder sb = new StringBuilder();
        sb.append("<div style='padding:4px 0;'>");
        for (final TreeNode child : root.children.values()) {
            renderTree(sb, child, child.name, 0);
        }
        sb.append("</div>");

        actorsPane.setText(html(sb.toString()));
    }

    private void renderTree(
        final StringBuilder sb,
        final TreeNode node,
        final String path,
        final int depth
    ) {
        final int indent = depth * 16;
        final boolean hasChildren = !node.children.isEmpty();
        final boolean isCollapsed = collapsed.contains(path);
        final String bullet = hasChildren ? (isCollapsed ? "&#9656;" : "&#9662;") : "&#8226;";
        final String nameColor = depth == 0
            ? RaggerTheme.hex(RaggerTheme.ACCENT)
            : RaggerTheme.hex(RaggerTheme.TEXT);
        final String dimColor = RaggerTheme.hex(RaggerTheme.TEXT_DIM);

        sb.append("<div style='padding:3px 0 3px ").append(indent).append("px;'>");

        if (hasChildren) {
            sb.append("<a href='toggle:").append(esc(path)).append("' style='color:")
                .append(dimColor).append("; text-decoration:none;'>").append(bullet).append(" </a>");
        } else {
            sb.append("<span style='color:").append(dimColor).append(";'>")
                .append(bullet).append(" </span>");
        }

        sb.append("<span style='color:").append(nameColor).append("; font-size:9px;'>")
            .append(esc(node.name)).append("</span>");

        // Copy source link (only for leaf actors that are actually loaded)
        if (node.fullName != null) {
            sb.append(" <a href='copy-source:").append(esc(node.fullName)).append("' style='color:")
                .append(RaggerTheme.hex(RaggerTheme.CODE))
                .append("; font-size:8px; text-decoration:none;'>[copy]</a>");

            sb.append(" <a href='stop-script:").append(esc(node.fullName)).append("' style='color:")
                .append(RaggerTheme.hex(RaggerTheme.TEXT_DIM))
                .append("; font-size:8px; text-decoration:none;'>[stop]</a>");
        }

        sb.append("</div>");

        if (!isCollapsed) {
            for (final TreeNode child : node.children.values()) {
                renderTree(sb, child, path + "/" + child.name, depth + 1);
            }
        }
    }

    // ── Templates tab rendering ─────────────────────────────────────────

    private void refreshTemplates() {
        final List<String> names = actorManager.listTemplates();

        if (names.isEmpty()) {
            templatesPane.setText(emptyState("No templates registered."));
            return;
        }

        Collections.sort(names);

        final StringBuilder sb = new StringBuilder();
        sb.append("<div style='padding:4px 0;'>");
        final String accentHex = RaggerTheme.hex(RaggerTheme.ACCENT);
        final String linkHex = RaggerTheme.hex(RaggerTheme.CODE);

        for (final String name : names) {
            sb.append("<div style='padding:3px 0;'>");
            sb.append("<span style='color:").append(accentHex).append(";'>&#9670; </span>");
            sb.append("<span style='color:").append(RaggerTheme.hex(RaggerTheme.TEXT)).append(";'>")
                .append(esc(name)).append("</span>");

            sb.append(" <a href='run-template:").append(esc(name)).append("' style='color:")
                .append(linkHex).append("; font-size:8px; text-decoration:none;'>[run]</a>");

            sb.append(" <a href='copy-template:").append(esc(name)).append("' style='color:")
                .append(linkHex).append("; font-size:8px; text-decoration:none;'>[copy]</a>");

            sb.append("</div>");
        }

        sb.append("</div>");
        templatesPane.setText(html(sb.toString()));
    }

    // ── HTML helpers ────────────────────────────────────────────────────

    private JEditorPane createHtmlPane() {
        final JEditorPane pane = new JEditorPane();
        pane.setContentType("text/html");
        pane.setEditable(false);
        pane.setOpaque(false);
        pane.setCaret(new DefaultCaret() {
            @Override
            public boolean isVisible() {
                return false;
            }

            @Override
            public boolean isSelectionVisible() {
                return false;
            }
        });
        pane.putClientProperty(JEditorPane.HONOR_DISPLAY_PROPERTIES, Boolean.TRUE);
        pane.setFont(RaggerTheme.FONT_SMALL);
        pane.setForeground(RaggerTheme.TEXT);
        pane.setBorder(new EmptyBorder(4, 8, 4, 8));

        // Handle link clicks
        pane.addHyperlinkListener(e -> {
            if (e.getEventType() == HyperlinkEvent.EventType.ACTIVATED) {
                handleLink(e.getDescription());
            }
        });

        return pane;
    }

    private void handleLink(final String href) {
        if (actorManager == null) {
            return;
        }

        if (href.startsWith("toggle:")) {
            final String path = href.substring("toggle:".length());
            if (!collapsed.remove(path)) {
                collapsed.add(path);
            }
            refreshActors();
            return;
        }

        if (href.startsWith("copy-source:")) {
            final String name = href.substring("copy-source:".length());
            final String source = actorManager.getSource(name);
            if (source != null) {
                copyToClipboard(source);
            }
        } else if (href.startsWith("copy-template:")) {
            final String name = href.substring("copy-template:".length());
            final String source = actorManager.getTemplate(name);
            if (source != null) {
                copyToClipboard(source);
            }
        } else if (href.startsWith("run-template:")) {
            final String name = href.substring("run-template:".length());
            final String source = actorManager.getTemplate(name);
            if (source != null) {
                actorManager.load(name, source);
            }
        } else if (href.startsWith("stop-script:")) {
            final String name = href.substring("stop-script:".length());
            actorManager.unload(name);
        }
    }

    private static void copyToClipboard(final String text) {
        Toolkit.getDefaultToolkit().getSystemClipboard()
            .setContents(new StringSelection(text), null);
    }

    private static JScrollPane wrap(final JEditorPane pane) {
        final JScrollPane scroll = new JScrollPane(pane);
        scroll.setBackground(RaggerTheme.BG);
        scroll.getViewport().setBackground(RaggerTheme.BG);
        scroll.setBorder(BorderFactory.createEmptyBorder());
        scroll.setHorizontalScrollBarPolicy(ScrollPaneConstants.HORIZONTAL_SCROLLBAR_NEVER);
        return scroll;
    }

    private static void styleTabPane(final JTabbedPane tabs) {
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

    private String html(final String body) {
        final String fontFamily = RaggerTheme.FONT.getFamily();
        return "<html><body style='"
            + "font-family:" + fontFamily + ",monospace;"
            + "font-size:9px;"
            + "color:" + RaggerTheme.hex(RaggerTheme.TEXT) + ";"
            + "background:" + RaggerTheme.hex(RaggerTheme.BG) + ";"
            + "margin:0; padding:0;"
            + "'>" + body + "</body></html>";
    }

    private static String emptyState(final String message) {
        return "<html><body style='text-align:center; padding:20px; color:"
            + RaggerTheme.hex(RaggerTheme.TEXT_DIMMER) + ";'>"
            + message + "</body></html>";
    }

    private static String esc(final String s) {
        return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("\"", "&quot;");
    }

    // ── Tree building ───────────────────────────────────────────────────

    private static class TreeNode {

        final String name;
        String fullName; // non-null only for nodes that are actual loaded scripts
        final LinkedHashMap<String, TreeNode> children = new LinkedHashMap<>();

        TreeNode(final String name) {
            this.name = name;
        }
    }
}
