package dev.ragger.plugin.scripting;

import net.runelite.client.ui.overlay.Overlay;
import net.runelite.client.ui.overlay.OverlayLayer;
import net.runelite.client.ui.overlay.OverlayPosition;

import java.awt.Dimension;
import java.awt.Graphics2D;

/**
 * Renders draw commands queued by Lua actors via OverlayApi.
 */
public class ActorOverlay extends Overlay {

    private final ActorManager actorManager;

    public ActorOverlay(final ActorManager actorManager) {
        this.actorManager = actorManager;
        setPosition(OverlayPosition.DYNAMIC);
        setLayer(OverlayLayer.ABOVE_SCENE);
    }

    @Override
    public Dimension render(final Graphics2D graphics) {
        actorManager.render(graphics);
        return null;
    }
}
