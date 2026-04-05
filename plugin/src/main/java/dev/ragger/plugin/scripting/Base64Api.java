package dev.ragger.plugin.scripting;

import party.iroiro.luajava.Lua;

import java.nio.charset.StandardCharsets;
import java.util.Base64;

/**
 * Lua binding for Base64 encode/decode.
 * Exposed as the global "base64" table in Lua scripts.
 *
 * Usage in Lua:
 *   local encoded = base64.encode("hello world")
 *   local decoded = base64.decode(encoded)
 */
public class Base64Api {

    private static final Base64.Encoder ENCODER = Base64.getEncoder();
    private static final Base64.Decoder DECODER = Base64.getDecoder();

    public void register(final Lua lua) {
        lua.createTable(0, 2);

        lua.push(this::encode);
        lua.setField(-2, "encode");

        lua.push(this::decode);
        lua.setField(-2, "decode");

        lua.setGlobal("base64");
    }

    /**
     * base64.encode(string) -> Base64-encoded string
     */
    private int encode(final Lua lua) {
        final String input = lua.toString(1);
        if (input == null) {
            lua.pushNil();
            return 1;
        }

        lua.push(ENCODER.encodeToString(input.getBytes(StandardCharsets.UTF_8)));
        return 1;
    }

    /**
     * base64.decode(string) -> decoded string
     */
    private int decode(final Lua lua) {
        final String input = lua.toString(1);
        if (input == null) {
            lua.pushNil();
            return 1;
        }

        try {
            lua.push(new String(DECODER.decode(input), StandardCharsets.UTF_8));
        } catch (final IllegalArgumentException e) {
            lua.error("base64.decode: invalid input");
        }

        return 1;
    }
}
