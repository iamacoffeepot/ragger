package dev.ragger.plugin.scripting;

import net.runelite.client.ui.overlay.Overlay;
import net.runelite.client.ui.overlay.OverlayLayer;
import net.runelite.client.ui.overlay.OverlayPosition;

import java.awt.*;

/**
 * Renders draw commands queued by Lua actors via OverlayApi.
 */
public class ActorOverlay extends Overlay {

    private final ActorManager actorManager;

    public ActorOverlay(ActorManager actorManager) {
        this.actorManager = actorManager;
        setPosition(OverlayPosition.DYNAMIC);
        setLayer(OverlayLayer.ABOVE_SCENE);
    }

    @Override
    public Dimension render(Graphics2D graphics) {
        actorManager.render(graphics);
        return null;
    }
}
