package dev.ragger.plugin.scripting;

import net.runelite.api.Client;

/**
 * Lua binding for reading and controlling the camera.
 * Exposed as the global "camera" table in Lua scripts.
 */
public class CameraApi {

    private final Client client;

    public CameraApi(Client client) {
        this.client = client;
    }

    // Position
    public int x() { return client.getCameraX(); }
    public int y() { return client.getCameraY(); }
    public int z() { return client.getCameraZ(); }

    // Angles
    public int yaw() { return client.getCameraYaw(); }
    public int pitch() { return client.getCameraPitch(); }

    // Targets
    public void set_yaw(int yaw) { client.setCameraYawTarget(yaw); }
    public void set_pitch(int pitch) { client.setCameraPitchTarget(pitch); }
    public void set_speed(float speed) { client.setCameraSpeed(speed); }

    // Camera mode
    public int mode() { return client.getCameraMode(); }
    public void set_mode(int mode) { client.setCameraMode(mode); }

    // Focal point
    public double focal_x() { return client.getCameraFocalPointX(); }
    public double focal_y() { return client.getCameraFocalPointY(); }
    public double focal_z() { return client.getCameraFocalPointZ(); }
    public void set_focal_x(double x) { client.setCameraFocalPointX(x); }
    public void set_focal_y(double y) { client.setCameraFocalPointY(y); }
    public void set_focal_z(double z) { client.setCameraFocalPointZ(z); }

    // Shake
    public boolean shake_disabled() { return client.isCameraShakeDisabled(); }
    public void set_shake_disabled(boolean disabled) { client.setCameraShakeDisabled(disabled); }
}
